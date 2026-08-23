from __future__ import annotations

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.database import IrisConnectionFactory, transaction
from app.domain import ProposalDocumentWrite, UpsertResult, utc_now
from app.embeddings import OpenAIEmbedder
from app.ingestion.camara import CamaraClient
from app.ingestion.camara.mapper import (
    author_write,
    history_write,
    mandate_write,
    proposition_write,
    topic_write,
)
from app.ingestion.chunking import PoliticalChunkBuilder, TokenChunker
from app.ingestion.http import HttpClient
from app.ingestion.matching import CandidateMatcher
from app.ingestion.tse import TseClient
from app.ingestion.tse.mapper import to_candidate
from app.ingestion.tse.parser import parse_candidates
from app.ingestion.tse.proposal_reader import read_proposals
from app.repositories import (
    CandidateRepository,
    IngestionRunRepository,
    PoliticalChunkRepository,
    PoliticalHistoryRepository,
    ProposalDocumentRepository,
    PropositionAuthorRepository,
    PropositionRepository,
    PropositionTopicRepository,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RunState:
    id: int
    failures: int = 0
    successes: int = 0


class IngestionPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.factory = IrisConnectionFactory(settings)
        self.http = HttpClient(
            settings.http_connect_timeout_seconds,
            settings.http_read_timeout_seconds,
            settings.http_max_retries,
        )
        self.tse = TseClient(settings, self.http)
        self.camara = CamaraClient(settings, self.http)

    def run(self) -> None:
        dataset = self.tse.dataset()
        with tempfile.TemporaryDirectory(prefix="iris-political-") as directory:
            root = Path(directory)
            self._tse_candidates(dataset, root)
            self._tse_proposals(dataset, root)
        self._camara()
        self._chunks_and_embeddings()

    def _tse_candidates(self, dataset, root: Path) -> None:  # noqa: ANN001
        resource = self.tse.candidate_resource(dataset)
        artifact = self.tse.download(resource, root / "candidates.zip")
        rows = parse_candidates(artifact.path)
        with self.factory.connection() as connection:
            runs = IngestionRunRepository(connection, self.settings.iris_sql_schema)
            candidates = CandidateRepository(connection, self.settings.iris_sql_schema)
            run = RunState(runs.start("TSE_CANDIDATES", self._parameters(), artifact.sha256))
            connection.commit()
            try:
                for start in range(0, len(rows), 500):
                    with transaction(connection):
                        for row in rows[start : start + 500]:
                            runs.increment(run.id, "RecordsRead")
                            if row.candidate is None:
                                run.failures += 1
                                runs.increment(run.id, "RecordsFailed")
                                continue
                            raw = row.candidate
                            if raw.election_year != self.settings.ingest_election_year:
                                runs.increment(run.id, "RecordsSkipped")
                                continue
                            if (
                                raw.state not in self.settings.ingest_states
                                or raw.office_name not in self.settings.ingest_offices
                            ):
                                runs.increment(run.id, "RecordsSkipped")
                                continue
                            result = candidates.upsert(
                                to_candidate(raw, resource.url, artifact.collected_at)
                            )
                            self._record(runs, run, result)
                self._finish(runs, run)
                connection.commit()
            except Exception as exc:
                self._fail(runs, run, exc, connection)
                raise

    def _tse_proposals(self, dataset, root: Path) -> None:  # noqa: ANN001
        resources = self.tse.proposal_resources(dataset, self.settings.ingest_states)
        downloads = [
            self.tse.download(item, root / f"proposal-{index}.zip")
            for index, item in enumerate(resources)
        ]
        source_hash = hashlib.sha256(
            "".join(item.sha256 for item in downloads).encode()
        ).hexdigest()
        with self.factory.connection() as connection:
            runs = IngestionRunRepository(connection, self.settings.iris_sql_schema)
            candidates = CandidateRepository(connection, self.settings.iris_sql_schema)
            documents = ProposalDocumentRepository(connection, self.settings.iris_sql_schema)
            run = RunState(runs.start("TSE_PROPOSALS", self._parameters(), source_hash))
            connection.commit()
            try:
                for resource, artifact in zip(resources, downloads, strict=True):
                    for proposal in read_proposals(artifact.path):
                        runs.increment(run.id, "RecordsRead")
                        candidate = candidates.find_by_tse_id(proposal.tse_id)
                        if candidate is None or not proposal.text:
                            run.failures += 1
                            runs.increment(run.id, "RecordsFailed")
                            continue
                        title = f"Proposta de governo - {candidate.ballot_name or candidate.name} - documento {proposal.sequence}"
                        value = ProposalDocumentWrite(
                            candidate.id,
                            proposal.year,
                            title,
                            resource.url,
                            resource.id,
                            proposal.file_name,
                            proposal.document_hash,
                            proposal.text,
                            artifact.collected_at,
                        )
                        with transaction(connection):
                            self._record(runs, run, documents.upsert(value))
                self._finish(runs, run)
                connection.commit()
            except Exception as exc:
                self._fail(runs, run, exc, connection)
                raise

    def _camara(self) -> None:
        with self.factory.connection() as connection:
            schema = self.settings.iris_sql_schema
            runs = IngestionRunRepository(connection, schema)
            candidates = CandidateRepository(connection, schema)
            histories = PoliticalHistoryRepository(connection, schema)
            propositions = PropositionRepository(connection, schema)
            authors = PropositionAuthorRepository(connection, schema)
            topics = PropositionTopicRepository(connection, schema)
            matcher = CandidateMatcher(self.camara, Path("app/ingestion/matching/overrides.json"))
            run = RunState(runs.start("CAMARA", self._parameters()))
            connection.commit()
            try:
                for candidate in candidates.list_for_matching():
                    runs.increment(run.id, "RecordsRead")
                    match = matcher.match(candidate)
                    with transaction(connection):
                        candidates.save_match(candidate.id, match)
                    if match.deputy_id is None:
                        runs.increment(run.id, "RecordsSkipped")
                        continue
                    self._candidate_camara(
                        connection,
                        run,
                        runs,
                        candidate.id,
                        match.deputy_id,
                        histories,
                        propositions,
                        authors,
                        topics,
                    )
                self._finish(runs, run)
                connection.commit()
            except Exception as exc:
                self._fail(runs, run, exc, connection)
                raise

    def _candidate_camara(
        self,
        connection,
        run: RunState,
        runs: IngestionRunRepository,
        candidate_id: int,
        deputy_id: int,
        histories: PoliticalHistoryRepository,
        propositions: PropositionRepository,
        authors: PropositionAuthorRepository,
        topics: PropositionTopicRepository,
    ) -> None:
        collected = utc_now()
        base = self.settings.camara_base_url.rstrip("/")
        history_items = self.camara.history(deputy_id)
        mandates = self.camara.external_mandates(deputy_id)
        with transaction(connection):
            for history_item in history_items:
                result = histories.upsert(
                    history_write(
                        candidate_id,
                        deputy_id,
                        history_item,
                        f"{base}/deputados/{deputy_id}/historico",
                        collected,
                    )
                )
                self._record(runs, run, result)
            for mandate_item in mandates:
                result = histories.upsert(
                    mandate_write(
                        candidate_id,
                        deputy_id,
                        mandate_item,
                        f"{base}/deputados/{deputy_id}/mandatosExternos",
                        collected,
                    )
                )
                self._record(runs, run, result)
        for summary in self.camara.propositions(deputy_id):
            try:
                detail = self.camara.proposition(summary.id)
                external_authors = self.camara.authors(summary.id)
                external_topics = self.camara.topics(summary.id)
                with transaction(connection):
                    proposition = propositions.upsert(
                        proposition_write(candidate_id, detail, collected)
                    )
                    self._record(runs, run, proposition)
                    for author_item in external_authors:
                        self._record(
                            runs,
                            run,
                            authors.upsert(author_write(proposition.id, author_item)),
                        )
                    for topic_item in external_topics:
                        self._record(
                            runs,
                            run,
                            topics.upsert(topic_write(proposition.id, topic_item)),
                        )
            except Exception:
                run.failures += 1
                with transaction(connection):
                    runs.increment(run.id, "RecordsFailed")
                LOGGER.exception("proposition ingestion failed", extra={"source_id": summary.id})

    def _chunks_and_embeddings(self) -> None:
        with self.factory.connection() as connection:
            schema = self.settings.iris_sql_schema
            chunk_repo = PoliticalChunkRepository(connection, schema)
            proposition_repo = PropositionRepository(connection, schema)
            history_repo = PoliticalHistoryRepository(connection, schema)
            document_repo = ProposalDocumentRepository(connection, schema)
            builder = PoliticalChunkBuilder(
                TokenChunker(
                    self.settings.embedding_model,
                    self.settings.chunk_size_tokens,
                    self.settings.chunk_overlap_tokens,
                ),
                PropositionAuthorRepository(connection, schema),
                PropositionTopicRepository(connection, schema),
            )
            for row in proposition_repo.list_for_chunks():
                with transaction(connection):
                    chunk_repo.replace_source(builder.proposition(row))
            for row in document_repo.list_for_chunks():
                chunks = builder.document(row)
                if chunks:
                    with transaction(connection):
                        chunk_repo.replace_source(chunks)
            for row in history_repo.list_for_chunks():
                with transaction(connection):
                    chunk_repo.replace_source(builder.history(row))
            embedder = OpenAIEmbedder(
                self.settings.llm_api_key,
                self.settings.embedding_model,
                self.settings.embedding_dimension,
            )
            while pending := chunk_repo.without_embedding():
                for chunk in pending:
                    vector = embedder.embed(chunk.content)
                    with transaction(connection):
                        chunk_repo.update_embedding(chunk.id, vector, embedder.model)

    def _parameters(self) -> dict:
        return {
            "electionYear": self.settings.ingest_election_year,
            "states": self.settings.ingest_states,
            "offices": self.settings.ingest_offices,
            "datasetId": self.settings.tse_dataset_id,
            "pageSize": self.settings.camara_page_size,
        }

    @staticmethod
    def _record(runs: IngestionRunRepository, state: RunState, result: UpsertResult) -> None:
        column = {
            "INSERTED": "RecordsCreated",
            "UPDATED": "RecordsUpdated",
            "UPDATED_CONFLICT": "RecordsUpdated",
            "UNCHANGED": "RecordsSkipped",
        }[result.action]
        runs.increment(state.id, column)
        state.successes += 1

    @staticmethod
    def _finish(runs: IngestionRunRepository, state: RunState) -> None:
        status = (
            "PARTIAL"
            if state.failures and state.successes
            else "FAILED"
            if state.failures
            else "SUCCESS"
        )
        runs.finish(state.id, status)

    @staticmethod
    def _fail(runs: IngestionRunRepository, state: RunState, exc: Exception, connection) -> None:  # noqa: ANN001
        connection.rollback()
        runs.finish(state.id, "FAILED", str(exc))
        connection.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    IngestionPipeline(get_settings()).run()


if __name__ == "__main__":
    main()
