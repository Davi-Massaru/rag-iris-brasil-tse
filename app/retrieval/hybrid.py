from __future__ import annotations

from app.domain import SearchResult

from .lexical import LexicalSearch
from .planner import QueryStrategy, plan_query
from .rrf import reciprocal_rank_fusion
from .structured import CoverageSearch, TopicFrequencySearch
from .vector import VectorSearch


class HybridSearch:
    def __init__(
        self,
        lexical: LexicalSearch,
        vector: VectorSearch,
        coverage: CoverageSearch | None = None,
        topic_frequency: TopicFrequencySearch | None = None,
    ) -> None:
        self.lexical = lexical
        self.vector = vector
        self.coverage = coverage
        self.topic_frequency = topic_frequency

    def search(
        self,
        query: str,
        candidate_id: int | None = None,
        source_type: str | None = None,
        top_k: int = 8,
    ) -> list[SearchResult]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        plan = plan_query(query, source_type)
        if (
            plan.strategy == QueryStrategy.DOCUMENT_COVERAGE
            and candidate_id is not None
            and self.coverage is not None
        ):
            return self.coverage.search(candidate_id, plan.source_type, top_k)
        if (
            plan.strategy == QueryStrategy.THEME_FREQUENCY
            and candidate_id is not None
            and self.topic_frequency is not None
        ):
            return self.topic_frequency.search(candidate_id, top_k)
        lexical = self.lexical.search(query, candidate_id, plan.source_type, 20)
        vector = self.vector.search(query, candidate_id, plan.source_type, 20)
        return reciprocal_rank_fusion((lexical, vector), top_k)
