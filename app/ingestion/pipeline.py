from __future__ import annotations

import hashlib
import logging
import tempfile
import threading
from collections import Counter
from concurrent.futures import Executor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.config import Settings, get_settings
from app.database import IrisConnectionFactory, transaction
from app.domain import ProposalDocumentWrite, UpsertResult, utc_now
from app.ingestion.camara import CamaraClient
from app.ingestion.camara.mapper import (
    author_write,
    history_write,
    mandate_write,
    proposition_write,
    topic_write,
)
from app.ingestion.chunk_index import ChunkIndexPipeline
from app.ingestion.http import HttpClient
from app.ingestion.matching import CandidateMatcher
from app.ingestion.tse import TseClient
from app.ingestion.tse.mapper import to_candidate
from app.ingestion.tse.parser import parse_candidates
from app.ingestion.tse.proposal_reader import read_proposals
from app.repositories import (
    CandidateRepository,
    IngestionRunRepository,
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
        self._worker_local = threading.local()
        self._worker_clients: list[HttpClient] = []
        self._worker_clients_lock = threading.Lock()

    def run(self) -> None:
        LOGGER.info(
            "ingestion pipeline started election_year=%d states=%s offices=%s embeddings_enabled=%s",
            self.settings.ingest_election_year,
            ",".join(self.settings.ingest_states),
            ",".join(self.settings.ingest_offices),
            bool(self.settings.llm_api_key),
        )
        dataset = self.tse.dataset()
        LOGGER.info("TSE dataset discovered dataset_id=%s", self.settings.tse_dataset_id)
        with tempfile.TemporaryDirectory(prefix="iris-political-") as directory:
            root = Path(directory)
            self._tse_candidates(dataset, root)
            self._tse_proposals(dataset, root)
        self._camara()
        self._chunks_and_embeddings()
        LOGGER.info("ingestion pipeline completed")

    def _tse_candidates(self, dataset, root: Path) -> None:  # noqa: ANN001
        resource = self.tse.candidate_resource(dataset)
        artifact = self.tse.download(resource, root / "candidates.zip")
        rows = parse_candidates(artifact.path)
        LOGGER.info(
            "TSE candidate artifact parsed resource_id=%s rows=%d sha256=%s",
            resource.id,
            len(rows),
            artifact.sha256[:12],
        )
        with self.factory.connection() as connection:
            runs = IngestionRunRepository(connection, self.settings.iris_sql_schema)
            candidates = CandidateRepository(connection, self.settings.iris_sql_schema)
            run = RunState(runs.start("TSE_CANDIDATES", self._parameters(), artifact.sha256))
            connection.commit()
            LOGGER.info("ingestion stage started stage=TSE_CANDIDATES run_id=%d", run.id)
            try:
                for start in range(0, len(rows), 500):
                    with transaction(connection):
                        counters: Counter[str] = Counter()
                        for row in rows[start : start + 500]:
                            counters["RecordsRead"] += 1
                            if row.candidate is None:
                                run.failures += 1
                                counters["RecordsFailed"] += 1
                                continue
                            raw = row.candidate
                            if raw.election_year != self.settings.ingest_election_year:
                                counters["RecordsSkipped"] += 1
                                continue
                            if (
                                raw.state not in self.settings.ingest_states
                                or raw.office_name not in self.settings.ingest_offices
                            ):
                                counters["RecordsSkipped"] += 1
                                continue
                            result = candidates.upsert(
                                to_candidate(raw, resource.url, artifact.collected_at)
                            )
                            self._record(counters, run, result)
                        runs.increment_many(run.id, counters)
                    LOGGER.info(
                        "ingestion progress stage=TSE_CANDIDATES run_id=%d processed=%d total=%d",
                        run.id,
                        min(start + 500, len(rows)),
                        len(rows),
                    )
                self._finish(runs, run)
                connection.commit()
            except Exception as exc:
                self._fail(runs, run, exc, connection)
                raise

    def _tse_proposals(self, dataset, root: Path) -> None:  # noqa: ANN001
        resources = self.tse.proposal_resources(dataset, self.settings.ingest_states)
        LOGGER.info("TSE proposal resources discovered count=%d", len(resources))
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
            LOGGER.info("ingestion stage started stage=TSE_PROPOSALS run_id=%d", run.id)
            try:
                for resource, artifact in zip(resources, downloads, strict=True):
                    resource_records = 0
                    for proposal in read_proposals(artifact.path):
                        resource_records += 1
                        with transaction(connection):
                            counters = Counter({"RecordsRead": 1})
                            candidate = candidates.find_by_tse_id(proposal.tse_id)
                            if candidate is None:
                                counters["RecordsSkipped"] += 1
                                runs.increment_many(run.id, counters)
                                continue
                            if not proposal.text:
                                run.failures += 1
                                counters["RecordsFailed"] += 1
                                runs.increment_many(run.id, counters)
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
                            self._record(counters, run, documents.upsert(value))
                            runs.increment_many(run.id, counters)
                    LOGGER.info(
                        "TSE proposal artifact processed run_id=%d resource_id=%s records=%d sha256=%s",
                        run.id,
                        resource.id,
                        resource_records,
                        artifact.sha256[:12],
                    )
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
            candidates_to_match = candidates.list_for_matching()
            LOGGER.info(
                "ingestion stage started stage=CAMARA run_id=%d candidates=%d",
                run.id,
                len(candidates_to_match),
            )
            ingested_candidates = 0
            try:
                with ThreadPoolExecutor(
                    max_workers=self.settings.camara_http_workers,
                    thread_name_prefix="camara-http",
                ) as executor:
                    for index, candidate in enumerate(candidates_to_match, start=1):
                        match = matcher.match(candidate)
                        counters = Counter({"RecordsRead": 1})
                        if (
                            match.deputy_id is None
                            or ingested_candidates >= self.settings.camara_max_matched_candidates
                        ):
                            counters["RecordsSkipped"] += 1
                        with transaction(connection):
                            candidates.save_match(candidate.id, match)
                            runs.increment_many(run.id, counters)
                        if match.deputy_id is None:
                            continue
                        if ingested_candidates >= self.settings.camara_max_matched_candidates:
                            continue
                        ingested_candidates += 1
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
                            executor,
                        )
                        if index % 25 == 0 or index == len(candidates_to_match):
                            LOGGER.info(
                                "ingestion progress stage=CAMARA run_id=%d processed=%d total=%d",
                                run.id,
                                index,
                                len(candidates_to_match),
                            )
                self._finish(runs, run)
                connection.commit()
            except Exception as exc:
                self._fail(runs, run, exc, connection)
                raise
            finally:
                self._close_worker_clients()

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
        executor: Executor,
    ) -> None:
        collected = utc_now()
        base = self.settings.camara_base_url.rstrip("/")
        cutoff = self.camara.lookback_start
        history_items = tuple(
            item
            for item in self.camara.history(deputy_id)
            if item.dataHora and item.dataHora[:10] >= cutoff.isoformat()
        )
        mandates = tuple(
            item
            for item in self.camara.external_mandates(deputy_id)
            if _mandate_overlaps(item.anoInicio, item.anoFim, cutoff.year)
        )
        LOGGER.info(
            "Câmara candidate ingestion started candidate_id=%d deputy_id=%d "
            "histories=%d mandates=%d proposition_limit=%d author_limit=%d",
            candidate_id,
            deputy_id,
            len(history_items),
            len(mandates),
            self.settings.camara_max_propositions_per_candidate,
            self.settings.camara_max_authors_per_proposition,
        )
        with transaction(connection):
            counters: Counter[str] = Counter()
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
                self._record(counters, run, result)
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
                self._record(counters, run, result)
            runs.increment_many(run.id, counters)
        summaries = tuple(self.camara.propositions(deputy_id))
        futures = {
            executor.submit(self._proposition_bundle, summary.id): summary for summary in summaries
        }
        for future in as_completed(futures):
            summary = futures[future]
            try:
                detail, external_authors, external_topics = future.result()
                with transaction(connection):
                    counters = Counter()
                    proposition = propositions.upsert(
                        proposition_write(candidate_id, detail, collected)
                    )
                    self._record(counters, run, proposition)
                    author_values = tuple(
                        author_write(proposition.id, item) for item in external_authors
                    )
                    topic_values = tuple(
                        topic_write(proposition.id, item) for item in external_topics
                    )
                    for result in authors.upsert_many(author_values):
                        self._record(counters, run, result)
                    for result in topics.upsert_many(topic_values):
                        self._record(counters, run, result)
                    runs.increment_many(run.id, counters)
            except Exception:
                run.failures += 1
                with transaction(connection):
                    runs.increment(run.id, "RecordsFailed")
                LOGGER.exception(
                    "proposition ingestion failed run_id=%d source_id=%d candidate_id=%d",
                    run.id,
                    summary.id,
                    candidate_id,
                )

    def _proposition_bundle(self, proposition_id: int):  # noqa: ANN202
        client = getattr(self._worker_local, "camara", None)
        if client is None:
            http = HttpClient(
                self.settings.http_connect_timeout_seconds,
                self.settings.http_read_timeout_seconds,
                self.settings.http_max_retries,
            )
            client = CamaraClient(self.settings, http)
            self._worker_local.camara = client
            with self._worker_clients_lock:
                self._worker_clients.append(http)
        return (
            client.proposition(proposition_id),
            client.authors(proposition_id),
            client.topics(proposition_id),
        )

    def _close_worker_clients(self) -> None:
        with self._worker_clients_lock:
            clients, self._worker_clients = self._worker_clients, []
        for client in clients:
            client.close()

    def _chunks_and_embeddings(self) -> None:
        LOGGER.info("RAG index stage started")
        ChunkIndexPipeline(self.settings, self.factory).run()

    def _parameters(self) -> dict:
        return {
            "electionYear": self.settings.ingest_election_year,
            "states": self.settings.ingest_states,
            "offices": self.settings.ingest_offices,
            "datasetId": self.settings.tse_dataset_id,
            "pageSize": self.settings.camara_page_size,
            "camaraLookbackYears": self.settings.camara_lookback_years,
            "camaraMaxMatchedCandidates": self.settings.camara_max_matched_candidates,
            "camaraMaxPropositionsPerCandidate": (
                self.settings.camara_max_propositions_per_candidate
            ),
            "camaraMaxAuthorsPerProposition": (self.settings.camara_max_authors_per_proposition),
        }

    @staticmethod
    def _record(counters: Counter[str], state: RunState, result: UpsertResult) -> None:
        column = {
            "INSERTED": "RecordsCreated",
            "UPDATED": "RecordsUpdated",
            "UPDATED_CONFLICT": "RecordsUpdated",
            "UNCHANGED": "RecordsSkipped",
        }[result.action]
        counters[column] += 1
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
        LOGGER.info(
            "ingestion stage completed run_id=%d status=%s successes=%d failures=%d",
            state.id,
            status,
            state.successes,
            state.failures,
        )

    @staticmethod
    def _fail(runs: IngestionRunRepository, state: RunState, exc: Exception, connection) -> None:  # noqa: ANN001
        connection.rollback()
        runs.finish(state.id, "FAILED", str(exc))
        connection.commit()
        LOGGER.exception(
            "ingestion stage failed run_id=%d error_type=%s",
            state.id,
            type(exc).__name__,
        )


def _mandate_overlaps(start_year: str | None, end_year: str | None, cutoff_year: int) -> bool:
    if start_year and start_year.isdigit() and int(start_year) > date.today().year:
        return False
    return not (end_year and end_year.isdigit() and int(end_year) < cutoff_year)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    IngestionPipeline(get_settings()).run()


if __name__ == "__main__":
    main()
