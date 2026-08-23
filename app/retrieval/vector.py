from __future__ import annotations

import json

from app.domain import SearchResult
from app.embeddings import Embedder
from app.repositories.base import RepositorySupport


class VectorSearch(RepositorySupport):
    def __init__(self, connection, schema: str, embedder: Embedder) -> None:  # noqa: ANN001
        super().__init__(connection, schema)
        self.embedder = embedder

    def search(
        self,
        query: str,
        candidate_id: int | None = None,
        source_type: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        if top_k <= 0 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100")
        clauses = ["Embedding IS NOT NULL"]
        params: list[object] = [json.dumps(self.embedder.embed(query), separators=(",", ":"))]
        if candidate_id is not None:
            clauses.append("Candidate=?")
            params.append(candidate_id)
        if source_type:
            clauses.append("SourceType=?")
            params.append(source_type)
        rows = self.all(
            f"""SELECT TOP {top_k} ID,Candidate,SourceType,SourceId,Title,Content,SourceUrl,
            MetadataJson,VECTOR_COSINE(Embedding,TO_VECTOR(?,DOUBLE)) AS Similarity
            FROM {self.table("PoliticalChunk")} WHERE {" AND ".join(clauses)}
            ORDER BY Similarity DESC,ID ASC""",
            tuple(params),
        )
        return [_result(row) for row in rows]


def _result(row: tuple) -> SearchResult:
    try:
        metadata = json.loads(str(row[7] or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    return SearchResult(
        chunk_id=int(row[0]),
        candidate_id=int(row[1]),
        source_type=str(row[2]),
        source_id=str(row[3]),
        title=str(row[4] or ""),
        content=str(row[5]),
        source_url=str(row[6] or ""),
        score=float(row[8]),
        metadata=metadata,
    )
