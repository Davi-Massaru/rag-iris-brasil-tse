from __future__ import annotations

import pytest

from app.api import create_app
from app.domain import SearchResult
from app.rag.service import RagAnswer

pytestmark = pytest.mark.unit
CANDIDATE = (
    1,
    "TSE1",
    "MARIA SILVA",
    "MARIA",
    "ABC",
    10,
    "DEPUTADO FEDERAL",
    "SP",
    1010,
    99,
    "MATCHED",
    100.0,
    "https://dadosabertos.tse.jus.br/fonte",
)
PROPOSITION = (
    8,
    900,
    "PL",
    10,
    2026,
    "Educação",
    "Ementa",
    "Detalhe",
    None,
    "Em análise",
    "https://dadosabertos.camara.leg.br/fonte",
)


class Cursor:
    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.rowcount = 0

    def execute(self, sql: str, params=()) -> None:  # noqa: ANN001
        if sql == "SELECT 1":
            self.rows = [(1,)]
        elif ".Candidate" in sql and "WHERE ID=?" in sql:
            self.rows = [CANDIDATE] if params == (1,) else []
        elif ".Candidate" in sql:
            self.rows = [CANDIDATE]
        elif ".Proposition" in sql:
            self.rows = [PROPOSITION]

    def fetchone(self):  # noqa: ANN201
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return self.rows

    def close(self) -> None:
        pass


class Connection:
    def __init__(self) -> None:
        self.closed = False

    def cursor(self) -> Cursor:
        return Cursor()

    def close(self) -> None:
        self.closed = True


class ConnectionFactory:
    def connect(self) -> Connection:
        return Connection()


class SearchStub:
    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        return [
            SearchResult(
                3,
                1,
                "PROPOSITION",
                "900",
                "Educação",
                "Ementa",
                "https://dadosabertos.camara.leg.br/fonte",
                0.5,
            )
        ]


class RagStub:
    def ask(self, _question: str, _candidate_id: int | None) -> RagAnswer:
        return RagAnswer("Resposta [E1]", ({"sourceUrl": "https://official"},))


class ServiceFactory:
    def search(self, _connection) -> SearchStub:  # noqa: ANN001
        return SearchStub()

    def rag(self, _connection) -> RagStub:  # noqa: ANN001
        return RagStub()


@pytest.fixture
def client(settings):  # noqa: ANN001, ANN201
    application = create_app(settings, ConnectionFactory(), ServiceFactory())
    application.config["TESTING"] = True
    return application.test_client()


def test_five_public_endpoints(client) -> None:  # noqa: ANN001
    candidate_fields = {
        "id",
        "tse_id",
        "name",
        "ballot_name",
        "party",
        "party_number",
        "office",
        "state",
        "candidate_number",
        "camara_deputy_id",
        "match_status",
        "match_confidence",
        "source_url",
    }
    listed_candidate = client.get("/candidates").get_json()["items"][0]
    detailed_candidate = client.get("/candidates/1").get_json()

    assert listed_candidate["tse_id"] == "TSE1"
    assert set(listed_candidate) == candidate_fields
    assert set(detailed_candidate) == candidate_fields
    assert detailed_candidate == listed_candidate
    assert client.get("/candidates/1/propositions").get_json()["items"][0]["camaraId"] == 900
    assert (
        client.post("/search", json={"query": "educação"}).get_json()["results"][0]["chunk_id"] == 3
    )
    assert (
        client.post("/ask", json={"question": "O quê?", "candidateId": 1}).get_json()["answer"]
        == "Resposta [E1]"
    )


def test_api_validation_and_not_found(client) -> None:  # noqa: ANN001
    invalid = client.post("/search", json={"query": "   "})
    missing = client.get("/candidates/404")

    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_request"
    assert missing.status_code == 404


def test_health_checks_database(client) -> None:  # noqa: ANN001
    assert client.get("/health").get_json() == {"status": "ok"}
