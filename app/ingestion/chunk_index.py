from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from app.config import Settings, get_settings
from app.database import IrisConnectionFactory, transaction
from app.domain import UpsertResult
from app.embeddings import OpenAIEmbedder
from app.ingestion.chunking import PoliticalChunkBuilder, TokenChunker
from app.repositories import (
    IngestionRunRepository,
    PoliticalChunkRepository,
    PoliticalHistoryRepository,
    ProposalDocumentRepository,
    PropositionAuthorRepository,
    PropositionRepository,
    PropositionTopicRepository,
)

LOGGER = logging.getLogger(__name__)


class ChunkIndexPipeline:
    """Rebuild recoverable text and embeddings from records already stored in IRIS."""

    def __init__(
        self,
        settings: Settings,
        connection_factory: IrisConnectionFactory | None = None,
        embedder_factory: Callable[[], OpenAIEmbedder] | None = None,
    ) -> None:
        self.settings = settings
        self.connection_factory = connection_factory or IrisConnectionFactory(settings)
        self.embedder_factory = embedder_factory or self._openai_embedder

    def run(self) -> None:
        with self.connection_factory.connection() as connection:
            schema = self.settings.iris_sql_schema
            runs = IngestionRunRepository(connection, schema)
            run_id = runs.start("RAG_INDEX", self._parameters())
            connection.commit()
            try:
                self._rebuild(connection, runs, run_id)
            except Exception as exc:
                connection.rollback()
                runs.increment(run_id, "RecordsFailed")
                runs.finish(run_id, "FAILED", str(exc))
                connection.commit()
                raise

    def _rebuild(self, connection, runs: IngestionRunRepository, run_id: int) -> None:  # noqa: ANN001
        schema = self.settings.iris_sql_schema
        chunks = PoliticalChunkRepository(connection, schema)
        propositions = PropositionRepository(connection, schema)
        histories = PoliticalHistoryRepository(connection, schema)
        documents = ProposalDocumentRepository(connection, schema)
        builder = PoliticalChunkBuilder(
            TokenChunker(
                self.settings.embedding_model,
                self.settings.chunk_size_tokens,
                self.settings.chunk_overlap_tokens,
            ),
            PropositionAuthorRepository(connection, schema),
            PropositionTopicRepository(connection, schema),
        )
        with transaction(connection):
            repaired = propositions.repair_invalid_years()
            if repaired:
                runs.increment(run_id, "RecordsUpdated", repaired)
        sources = (
            (propositions.list_for_chunks(), builder.proposition),
            (documents.list_for_chunks(), builder.document),
            (histories.list_for_chunks(), builder.history),
        )
        for rows, build in sources:
            for row in rows:
                runs.increment(run_id, "RecordsRead")
                values = build(row)
                if not values:
                    runs.increment(run_id, "RecordsFailed")
                    raise ValueError("source produced no recoverable chunks")
                with transaction(connection):
                    results = chunks.replace_source(values)
                    self._record(runs, run_id, results)
        pending = chunks.without_embedding(self.settings.embedding_batch_size)
        if pending and not self.settings.llm_api_key:
            pending_count = chunks.pending_embedding_count()
            runs.increment(run_id, "RecordsFailed", pending_count)
            runs.finish(
                run_id,
                "PARTIAL",
                f"{pending_count} chunks rebuilt but embeddings are pending because "
                "LLM_API_KEY is absent",
            )
            connection.commit()
            return
        embedder = self.embedder_factory() if pending else None
        embedded = 0
        while pending and embedder is not None:
            vectors = embedder.embed_many([item.content for item in pending])
            with transaction(connection):
                for chunk, vector in zip(pending, vectors, strict=True):
                    chunks.update_embedding(chunk.id, vector, embedder.model)
                    runs.increment(run_id, "RecordsUpdated")
                    embedded += 1
            LOGGER.info("embedding batch completed total_embedded=%d", embedded)
            pending = chunks.without_embedding(self.settings.embedding_batch_size)
        runs.finish(run_id, "SUCCESS")
        connection.commit()
        LOGGER.info("RAG index completed run_id=%d embedded=%d", run_id, embedded)

    @staticmethod
    def _record(
        runs: IngestionRunRepository,
        run_id: int,
        results: Sequence[UpsertResult],
    ) -> None:
        for result in results:
            column = "RecordsCreated" if result.action == "INSERTED" else "RecordsSkipped"
            runs.increment(run_id, column)

    def _openai_embedder(self) -> OpenAIEmbedder:
        return OpenAIEmbedder(
            self.settings.llm_api_key,
            self.settings.embedding_model,
            self.settings.embedding_dimension,
        )

    def _parameters(self) -> dict:
        return {
            "chunkSizeTokens": self.settings.chunk_size_tokens,
            "chunkOverlapTokens": self.settings.chunk_overlap_tokens,
            "embeddingModel": self.settings.embedding_model,
            "embeddingBatchSize": self.settings.embedding_batch_size,
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ChunkIndexPipeline(get_settings()).run()


if __name__ == "__main__":
    main()
