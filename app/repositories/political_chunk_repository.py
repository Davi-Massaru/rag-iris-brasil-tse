from __future__ import annotations

import json
from collections.abc import Sequence

from app.domain import Chunk, ChunkWrite, UpsertResult, utc_now

from .base import RepositorySupport


class PoliticalChunkRepository(RepositorySupport):
    def replace_source(self, chunks: Sequence[ChunkWrite]) -> list[UpsertResult]:
        if not chunks:
            return []
        source = (chunks[0].candidate_id, chunks[0].source_type, chunks[0].source_id)
        if any((item.candidate_id, item.source_type, item.source_id) != source for item in chunks):
            raise ValueError("chunks must share one source")
        keep = {(item.chunk_index, item.content_hash) for item in chunks}
        rows = self.all(
            f"""SELECT ID,ChunkIndex,ContentHash FROM {self.table("PoliticalChunk")}
            WHERE Candidate=? AND SourceType=? AND SourceId=?""",
            source,
        )
        existing = {(int(row[1]), str(row[2])): int(row[0]) for row in rows}
        for row in rows:
            if (int(row[1]), str(row[2])) not in keep:
                self.execute(
                    f"DELETE FROM {self.table('PoliticalChunk')} WHERE ID=?", (int(row[0]),)
                )
        results: list[UpsertResult | None] = []
        inserted = False
        for item in chunks:
            current_id = existing.get((item.chunk_index, item.content_hash))
            if current_id is not None:
                results.append(UpsertResult(current_id, "UNCHANGED"))
                continue
            self._insert(item)
            results.append(None)
            inserted = True
        if inserted:
            rows = self.all(
                f"""SELECT ID,ChunkIndex,ContentHash FROM {self.table("PoliticalChunk")}
                WHERE Candidate=? AND SourceType=? AND SourceId=?""",
                source,
            )
            current = {(int(row[1]), str(row[2])): int(row[0]) for row in rows}
        else:
            current = existing
        return [
            result
            if result is not None
            else UpsertResult(current[(item.chunk_index, item.content_hash)], "INSERTED")
            for item, result in zip(chunks, results, strict=True)
        ]

    def upsert(self, value: ChunkWrite) -> UpsertResult:
        row = self.one(
            f"""SELECT ID FROM {self.table("PoliticalChunk")}
            WHERE Candidate=? AND SourceType=? AND SourceId=?
            AND ChunkIndex=? AND ContentHash=?""",
            (
                value.candidate_id,
                value.source_type,
                value.source_id,
                value.chunk_index,
                value.content_hash,
            ),
        )
        if row:
            return UpsertResult(int(row[0]), "UNCHANGED")
        self._insert(value)
        inserted = self.one(
            f"""SELECT ID FROM {self.table("PoliticalChunk")}
            WHERE Candidate=? AND SourceType=? AND SourceId=?
            AND ChunkIndex=? AND ContentHash=?""",
            (
                value.candidate_id,
                value.source_type,
                value.source_id,
                value.chunk_index,
                value.content_hash,
            ),
        )
        return UpsertResult(int(inserted[0]), "INSERTED")

    def _insert(self, value: ChunkWrite) -> None:
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("PoliticalChunk")}
            (Candidate,SourceType,SourceId,ChunkIndex,Title,Content,SourceUrl,MetadataJson,
             ContentHash,TokenCount,SourceCollectedAt,CreatedAt,UpdatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value.candidate_id,
                value.source_type,
                value.source_id,
                value.chunk_index,
                value.title,
                value.content,
                value.source_url,
                value.metadata_json,
                value.content_hash,
                value.token_count,
                value.collected_at,
                now,
                now,
            ),
        )

    def without_embedding(self, limit: int = 100) -> list[Chunk]:
        rows = self.all(
            f"""SELECT TOP {int(limit)} ID,Candidate,SourceType,SourceId,Title,Content,
            SourceUrl,MetadataJson,TokenCount FROM {self.table("PoliticalChunk")}
            WHERE Embedding IS NULL ORDER BY ID"""
        )
        return [_chunk(row) for row in rows]

    def pending_embedding_count(self) -> int:
        row = self.one(
            f"SELECT COUNT(*) FROM {self.table('PoliticalChunk')} WHERE Embedding IS NULL"
        )
        return int(row[0]) if row else 0

    def update_embedding(self, chunk_id: int, vector: list[float], model: str) -> None:
        if len(vector) != 1536:
            raise ValueError(f"embedding must contain 1536 values, got {len(vector)}")
        serialized = json.dumps(vector, separators=(",", ":"))
        self.execute(
            f"""UPDATE {self.table("PoliticalChunk")}
            SET Embedding=TO_VECTOR(?,DOUBLE),EmbeddingModel=?,UpdatedAt=? WHERE ID=?""",
            (serialized, model, utc_now(), chunk_id),
        )


def _chunk(row: tuple) -> Chunk:
    return Chunk(
        id=int(row[0]),
        candidate_id=int(row[1]),
        source_type=str(row[2]),
        source_id=str(row[3]),
        title=str(row[4] or ""),
        content=str(row[5]),
        source_url=str(row[6] or ""),
        metadata_json=str(row[7] or "{}"),
        token_count=int(row[8] or 0),
    )
