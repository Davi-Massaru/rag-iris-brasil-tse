from __future__ import annotations

from app.config import Settings
from app.embeddings import OpenAIEmbedder
from app.rag import OpenAILanguageModel, RagContextLoader, RagService
from app.repositories import (
    CandidateRepository,
    PoliticalHistoryRepository,
    ProposalDocumentRepository,
    PropositionAuthorRepository,
    PropositionRepository,
    PropositionTopicRepository,
)
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
        schema = self.settings.iris_sql_schema
        candidates = CandidateRepository(connection, schema)
        context_loader = RagContextLoader(
            candidates,
            PropositionRepository(connection, schema),
            ProposalDocumentRepository(connection, schema),
            PoliticalHistoryRepository(connection, schema),
            PropositionAuthorRepository(connection, schema),
            PropositionTopicRepository(connection, schema),
        )
        return RagService(
            self.search(connection),
            model,
            candidates,
            context_loader,
        )
