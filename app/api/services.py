from __future__ import annotations

from app.config import Settings
from app.embeddings import OpenAIEmbedder
from app.rag import OpenAILanguageModel, RagService
from app.repositories import CandidateRepository
from app.retrieval import (
    CoverageSearch,
    HybridSearch,
    LexicalSearch,
    TopicFrequencySearch,
    VectorSearch,
)


class ServiceFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, connection) -> HybridSearch:  # noqa: ANN001
        embedder = OpenAIEmbedder(
            self.settings.llm_api_key,
            self.settings.embedding_model,
            self.settings.embedding_dimension,
        )
        schema = self.settings.iris_sql_schema
        return HybridSearch(
            LexicalSearch(connection, schema),
            VectorSearch(connection, schema, embedder),
            CoverageSearch(connection, schema),
            TopicFrequencySearch(connection, schema),
        )

    def rag(self, connection) -> RagService:  # noqa: ANN001
        model = OpenAILanguageModel(
            self.settings.llm_api_key,
            self.settings.llm_model,
            self.settings.llm_max_output_tokens,
        )
        return RagService(
            self.search(connection),
            model,
            CandidateRepository(connection, self.settings.iris_sql_schema),
        )
