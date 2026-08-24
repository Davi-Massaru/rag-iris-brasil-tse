from __future__ import annotations

import os
from datetime import date, datetime
from uuid import uuid4

import pytest

from app.config import Settings
from app.database import IrisConnectionFactory, transaction
from app.domain import CandidateWrite, ChunkWrite, HistoryWrite, ProposalDocumentWrite
from app.repositories import (
    CandidateRepository,
    IngestionRunRepository,
    PoliticalChunkRepository,
    PoliticalHistoryRepository,
    ProposalDocumentRepository,
)
from app.retrieval import HybridSearch, LexicalSearch, VectorSearch

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_IRIS_TESTS") != "1",
        reason="set RUN_IRIS_TESTS=1 with the IRIS container running",
    ),
]


class StaticEmbedder:
    model = "integration-test"

    def embed(self, text: str) -> list[float]:
        del text
        return [1.0, *([0.0] * 1535)]


@pytest.fixture
def connection():  # noqa: ANN201
    settings = Settings(
        _env_file=None,
        iris_host="localhost",
        iris_port=1972,
        iris_namespace="IRISAPP",
        iris_username="_SYSTEM",
        iris_password="SYS",
    )
    with IrisConnectionFactory(settings).connection() as active:
        yield active


def candidate_value(tse_id: str, ballot_name: str = "TESTE") -> CandidateWrite:
    return CandidateWrite(
        tse_id=tse_id,
        name="CANDIDATO DE INTEGRAÇÃO",
        ballot_name=ballot_name,
        party="TST",
        party_number=99,
        office="DEPUTADO FEDERAL",
        state="SP",
        candidate_number=9999,
        source_url="https://dadosabertos.tse.jus.br/teste",
        collected_at=datetime(2026, 1, 1),
    )


def test_repository_transaction_vector_and_hybrid_search(connection) -> None:  # noqa: ANN001
    schema = "IRISPolitical_Model"
    candidates = CandidateRepository(connection, schema)
    chunks = PoliticalChunkRepository(connection, schema)
    tse_id = f"TEST-{uuid4().hex}"
    rollback_tse_id = f"ROLL-{uuid4().hex}"
    candidate_id: int | None = None
    try:
        with transaction(connection):
            inserted = candidates.upsert(candidate_value(tse_id))
        candidate_id = inserted.id
        assert inserted.action == "INSERTED"

        with transaction(connection):
            unchanged = candidates.upsert(candidate_value(tse_id))
            updated = candidates.upsert(candidate_value(tse_id, "TESTE ATUALIZADO"))
        assert unchanged.action == "UNCHANGED"
        assert updated.action == "UPDATED"
        found = candidates.find_by_id(candidate_id)
        assert found is not None
        assert found.ballot_name == "TESTE ATUALIZADO"

        with pytest.raises(RuntimeError, match="rollback"), transaction(connection):
            candidates.upsert(candidate_value(rollback_tse_id))
            raise RuntimeError("rollback")
        assert candidates.find_by_tse_id(rollback_tse_id) is None

        chunk = ChunkWrite(
            candidate_id=candidate_id,
            source_type="PROPOSITION",
            source_id=f"TEST-{uuid4().hex}",
            chunk_index=0,
            title="Educação e tecnologia",
            content="Proposta oficial sobre educação pública e inteligência artificial.",
            source_url="https://dadosabertos.camara.leg.br/teste",
            metadata_json='{"test":true}',
            content_hash=uuid4().hex * 2,
            token_count=8,
            collected_at=datetime(2026, 1, 1),
        )
        with transaction(connection):
            stored = chunks.upsert(chunk)
            chunks.update_embedding(stored.id, StaticEmbedder().embed("query"), "test")

        retrieval = HybridSearch(
            LexicalSearch(connection, schema),
            VectorSearch(connection, schema, StaticEmbedder()),
        )
        results = retrieval.search("educação", candidate_id=candidate_id, top_k=5)

        assert results
        assert results[0].chunk_id == stored.id
        assert results[0].metadata == {"test": True}
    finally:
        if candidate_id is not None:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"DELETE FROM {schema}.PoliticalChunk WHERE Candidate=?",
                    (candidate_id,),
                )
                cursor.execute(
                    f"DELETE FROM {schema}.Candidate WHERE ID=?",
                    (candidate_id,),
                )
                cursor.execute(
                    f"DELETE FROM {schema}.Candidate WHERE TseId=?",
                    (rollback_tse_id,),
                )
                connection.commit()
            finally:
                cursor.close()


def test_streams_and_ingestion_audit(connection) -> None:  # noqa: ANN001
    schema = "IRISPolitical_Model"
    candidates = CandidateRepository(connection, schema)
    histories = PoliticalHistoryRepository(connection, schema)
    documents = ProposalDocumentRepository(connection, schema)
    runs = IngestionRunRepository(connection, schema)
    tse_id = f"TEST-{uuid4().hex}"
    candidate_id: int | None = None
    run_id: int | None = None
    try:
        with transaction(connection):
            candidate_id = candidates.upsert(candidate_value(tse_id)).id
            history = histories.upsert(
                HistoryWrite(
                    candidate_id=candidate_id,
                    institution="CAMARA",
                    position="DEPUTADO FEDERAL",
                    party="TST",
                    state="SP",
                    start_date=date(2023, 1, 1),
                    end_date=None,
                    external_id=f"HIST-{uuid4().hex}",
                    situation="Em exercício",
                    source_url="https://dadosabertos.camara.leg.br/teste",
                    collected_at=datetime(2026, 1, 1),
                    raw_json='{"nome":"Integração"}',
                )
            )
            document = documents.upsert(
                ProposalDocumentWrite(
                    candidate_id=candidate_id,
                    election_year=2026,
                    title="Plano de governo",
                    source_url="https://dadosabertos.tse.jus.br/teste.pdf",
                    resource_id="resource-test",
                    file_name="proposal.pdf",
                    document_hash=uuid4().hex * 2,
                    raw_text="[Página 1]\nEducação pública com tecnologia.",
                    collected_at=datetime(2026, 1, 1),
                )
            )
            run_id = runs.start("TSE_CANDIDATES", {"year": 2026}, "0" * 64)
            runs.increment(run_id, "RecordsRead", 2)
            runs.increment(run_id, "RecordsCreated", 1)
            runs.finish(run_id, "SUCCESS")

        history_row = histories.one(
            f"SELECT RawJson FROM {schema}.PoliticalHistory WHERE ID=?", (history.id,)
        )
        document_row = documents.one(
            f"SELECT RawText FROM {schema}.ProposalDocument WHERE ID=?", (document.id,)
        )
        document_source = next(
            row for row in documents.list_for_chunks() if int(row[0]) == document.id
        )
        run_row = runs.one(
            f"SELECT Status,RecordsRead,RecordsCreated FROM {schema}.IngestionRun WHERE ID=?",
            (run_id,),
        )

        assert "Integração" in str(history_row[0])
        assert "Educação pública" in str(document_row[0])
        assert document_source[8] == "[Página 1]\nEducação pública com tecnologia."
        assert tuple(run_row) == ("SUCCESS", 2, 1)
    finally:
        cursor = connection.cursor()
        try:
            if candidate_id is not None:
                cursor.execute(
                    f"DELETE FROM {schema}.PoliticalHistory WHERE Candidate=?",
                    (candidate_id,),
                )
                cursor.execute(
                    f"DELETE FROM {schema}.ProposalDocument WHERE Candidate=?",
                    (candidate_id,),
                )
                cursor.execute(
                    f"DELETE FROM {schema}.Candidate WHERE ID=?",
                    (candidate_id,),
                )
            if run_id is not None:
                cursor.execute(f"DELETE FROM {schema}.IngestionRun WHERE ID=?", (run_id,))
            connection.commit()
        finally:
            cursor.close()
