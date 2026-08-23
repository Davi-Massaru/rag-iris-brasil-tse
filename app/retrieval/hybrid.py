from __future__ import annotations

from app.domain import SearchResult

from .lexical import LexicalSearch
from .rrf import reciprocal_rank_fusion
from .vector import VectorSearch


class HybridSearch:
    def __init__(self, lexical: LexicalSearch, vector: VectorSearch) -> None:
        self.lexical = lexical
        self.vector = vector

    def search(
        self,
        query: str,
        candidate_id: int | None = None,
        source_type: str | None = None,
        top_k: int = 8,
    ) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        lexical = self.lexical.search(query, candidate_id, source_type, 20)
        vector = self.vector.search(query, candidate_id, source_type, 20)
        return reciprocal_rank_fusion((lexical, vector), top_k)
