from __future__ import annotations

from app.config import Settings
from app.embeddings import OpenAIEmbedder
from app.rag import OpenAILanguageModel, RagService
from app.retrieval import HybridSearch, LexicalSearch, VectorSearch


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
        )

    def rag(self, connection) -> RagService:  # noqa: ANN001
        model = OpenAILanguageModel(
            self.settings.llm_api_key,
            self.settings.llm_model,
        )
        return RagService(self.search(connection), model)
