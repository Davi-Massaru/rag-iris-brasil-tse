from __future__ import annotations

from app.domain import ProposalDocumentWrite, UpsertResult, utc_now

from .base import RepositorySupport


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
        return self.all(
            f"""SELECT ID,Candidate,ElectionYear,Title,SourceUrl,SourceResourceId,FileName,
            DocumentHash,RawText,SourceCollectedAt FROM {self.table("ProposalDocument")} ORDER BY ID"""
        )
