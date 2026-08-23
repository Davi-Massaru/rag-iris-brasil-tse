from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.database import IrisConnectionFactory, transaction
from app.repositories import CandidateRepository

pytestmark = pytest.mark.unit


class ConnectionSpy:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_transaction_commits_success() -> None:
    connection = ConnectionSpy()

    with transaction(connection):
        pass

    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_transaction_rolls_back_and_reraises() -> None:
    connection = ConnectionSpy()

    with pytest.raises(RuntimeError, match="failure"), transaction(connection):
        raise RuntimeError("failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_connection_factory_uses_embedded_iris_without_tcp(monkeypatch) -> None:  # noqa: ANN001
    state = {"level": 0, "commits": 0, "rollbacks": 0}

    class Result(list):
        rowcount = 1

    def tstart() -> None:
        state["level"] += 1

    def tcommit() -> None:
        state["level"] -= 1
        state["commits"] += 1

    def trollbackone() -> None:
        state["level"] -= 1
        state["rollbacks"] += 1

    embedded_iris = SimpleNamespace(
        sql=SimpleNamespace(exec=lambda _sql, *_params: Result([[1]])),
        tstart=tstart,
        tcommit=tcommit,
        trollbackone=trollbackone,
    )
    monkeypatch.setitem(sys.modules, "iris", embedded_iris)

    connection = IrisConnectionFactory(Settings(_env_file=None)).connect()
    cursor = connection.cursor()
    cursor.execute("SELECT 1")

    assert cursor.fetchone() == [1]
    assert cursor.rowcount == -1
    assert state["level"] == 1

    connection.commit()
    connection.close()

    assert state == {"level": 0, "commits": 1, "rollbacks": 0}


def test_embedded_cursor_treats_iris_eof_as_end_of_result(monkeypatch) -> None:  # noqa: ANN001
    class EmptyResult:
        def __iter__(self):  # noqa: ANN204
            return self

        def __next__(self):  # noqa: ANN204
            raise EOFError

    embedded_iris = SimpleNamespace(
        sql=SimpleNamespace(exec=lambda _sql, *_params: EmptyResult()),
        tstart=lambda: None,
        tcommit=lambda: None,
        trollbackone=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "iris", embedded_iris)

    connection = IrisConnectionFactory(Settings(_env_file=None)).connect()
    cursor = connection.cursor()
    cursor.execute("SELECT 1 WHERE 1 = 0")

    assert cursor.fetchone() is None
    assert cursor.fetchall() == []


def test_embedded_cursor_normalizes_temporal_parameters(monkeypatch) -> None:  # noqa: ANN001
    captured: list[object] = []

    def execute(_sql, *params):  # noqa: ANN001, ANN202
        captured.extend(params)
        return []

    embedded_iris = SimpleNamespace(
        sql=SimpleNamespace(exec=execute),
        tstart=lambda: None,
        tcommit=lambda: None,
        trollbackone=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "iris", embedded_iris)

    connection = IrisConnectionFactory(Settings(_env_file=None)).connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO Example (CreatedAt, EventDate, Counter, OptionalId) VALUES (?, ?, ?, ?)",
        (datetime(2026, 8, 23, 17, 42, 3, 123456), date(2026, 8, 23), 7, None),
    )

    assert captured == ["2026-08-23 17:42:03.123456", 67805, 7, ""]


def test_embedded_cursor_logs_parameter_types_on_failure(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:  # noqa: ANN001
    def execute(_sql, *_params):  # noqa: ANN001, ANN202
        raise RuntimeError("driver rejected parameter")

    embedded_iris = SimpleNamespace(
        sql=SimpleNamespace(exec=execute),
        tstart=lambda: None,
        tcommit=lambda: None,
        trollbackone=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "iris", embedded_iris)

    connection = IrisConnectionFactory(Settings(_env_file=None)).connect()
    cursor = connection.cursor()

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        cursor.execute("INSERT INTO Example (CreatedAt) VALUES (?)", (datetime(2026, 8, 23),))

    assert "embedded SQL execution failed" in caplog.text
    assert "datetime" in caplog.text
    assert "2026-08-23 00:00:00" not in caplog.text


def test_candidate_repository_treats_embedded_empty_optional_values_as_null() -> None:
    class Cursor:
        rowcount = -1

        def execute(self, _sql, _params):  # noqa: ANN001, ANN201
            return None

        def fetchone(self):  # noqa: ANN201
            return (1, "TSE-1", "NOME", "", "", "", "CARGO", "SP", "", "", "", "", "")

        def close(self) -> None:
            return None

    connection = SimpleNamespace(cursor=lambda: Cursor())

    candidate = CandidateRepository(connection, "IRISPolitical_Model").find_by_tse_id("TSE-1")

    assert candidate is not None
    assert candidate.ballot_name is None
    assert candidate.party_number is None
    assert candidate.camara_deputy_id is None
    assert candidate.match_confidence is None
