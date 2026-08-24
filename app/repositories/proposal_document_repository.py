from __future__ import annotations

from app.domain import ProposalDocumentWrite, UpsertResult, utc_now

from .base import RepositorySupport

STREAM_READ_SIZE = 30_000


class ProposalDocumentRepository(RepositorySupport):
    def upsert(self, value: ProposalDocumentWrite) -> UpsertResult:
        row = self.one(
            f"""SELECT ID,ElectionYear,Title,SourceUrl,SourceResourceId,FileName
            FROM {self.table("ProposalDocument")} WHERE Candidate=? AND DocumentHash=?""",
            (value.candidate_id, value.document_hash),
        )
        fields = (
            value.election_year,
            value.title,
            value.source_url,
            value.resource_id,
            value.file_name,
        )
        if row and tuple(row[1:]) == fields:
            return UpsertResult(int(row[0]), "UNCHANGED")
        if row:
            self.execute(
                f"""UPDATE {self.table("ProposalDocument")} SET ElectionYear=?,Title=?,
                SourceUrl=?,SourceResourceId=?,FileName=?,RawText=?,SourceCollectedAt=?,
                UpdatedAt=? WHERE ID=?""",
                (*fields, value.raw_text, value.collected_at, utc_now(), int(row[0])),
            )
            return UpsertResult(int(row[0]), "UPDATED")
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("ProposalDocument")}
            (Candidate,ElectionYear,Title,SourceUrl,SourceResourceId,FileName,DocumentHash,
             RawText,SourceCollectedAt,CreatedAt,UpdatedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value.candidate_id,
                *fields,
                value.document_hash,
                value.raw_text,
                value.collected_at,
                now,
                now,
            ),
        )
        inserted = self.one(
            f"SELECT ID FROM {self.table('ProposalDocument')} WHERE Candidate=? AND DocumentHash=?",
            (value.candidate_id, value.document_hash),
        )
        return UpsertResult(int(inserted[0]), "INSERTED")

    def list_for_chunks(self) -> list[tuple]:
        rows = self.all(
            f"""SELECT ID,Candidate,ElectionYear,Title,SourceUrl,SourceResourceId,FileName,
            DocumentHash,CHAR_LENGTH(RawText),SourceCollectedAt
            FROM {self.table("ProposalDocument")} ORDER BY ID"""
        )
        return [
            (*row[:8], self._read_raw_text(int(row[0]), int(row[8] or 0)), row[9]) for row in rows
        ]

    def _read_raw_text(self, document_id: int, expected_length: int) -> str:
        """Materialize an IRIS character stream through portable SQL fragments.

        Embedded SQL returns a serialized stream reference when a stream column is
        selected directly. SUBSTRING dereferences the stream and works in both the
        Embedded Python and DB-API adapters.
        """
        if expected_length <= 0:
            return ""
        parts: list[str] = []
        for start in range(1, expected_length + 1, STREAM_READ_SIZE):
            row = self.one(
                f"""SELECT SUBSTRING(RawText,?,?)
                FROM {self.table("ProposalDocument")} WHERE ID=?""",
                (start, STREAM_READ_SIZE, document_id),
            )
            if row is None:
                raise RuntimeError(f"proposal document {document_id} disappeared during read")
            parts.append(str(row[0] or ""))
        content = "".join(parts)
        if len(content) != expected_length:
            raise RuntimeError(
                f"proposal document {document_id} stream length mismatch: "
                f"expected {expected_length}, got {len(content)}"
            )
        return content
