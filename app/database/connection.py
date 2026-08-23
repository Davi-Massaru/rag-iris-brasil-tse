from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from importlib import import_module
from typing import Any, Protocol, cast

from app.config import Settings

LOGGER = logging.getLogger(__name__)
IRIS_DATE_EPOCH = date(1840, 12, 31)


class _EmbeddedIrisSql(Protocol):
    def exec(self, sql: str, *params: Any) -> Iterator[Any]: ...


class _EmbeddedIrisApi(Protocol):
    sql: _EmbeddedIrisSql

    def tstart(self) -> None: ...

    def tcommit(self) -> None: ...

    def trollbackone(self) -> None: ...


def _embedded_iris() -> _EmbeddedIrisApi:
    """Load the vendor API without relying on its inaccurate type declarations."""
    return cast(_EmbeddedIrisApi, import_module("iris"))


def _embedded_parameter(value: Any) -> Any:
    """Convert Python temporal values to formats accepted by IRIS Embedded SQL."""
    # Embedded Python exposes SQL NULL as the IRIS logical empty string. Passing
    # Python None directly creates a %SYS.Python object reference instead.
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="microseconds")
    if isinstance(value, date):
        return (value - IRIS_DATE_EPOCH).days
    return value


def _statement_summary(sql: str) -> str:
    """Return useful SQL context without logging parameter values."""
    return " ".join(sql.split())[:160]


class EmbeddedIrisCursor:
    def __init__(self, connection: EmbeddedIrisConnection) -> None:
        self.connection = connection
        self._rows: Iterator[Any] = iter(())
        self.rowcount = -1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.connection._ensure_transaction()
        normalized = tuple(_embedded_parameter(value) for value in params)
        try:
            result = _embedded_iris().sql.exec(sql, *normalized)
        except Exception:
            LOGGER.exception(
                "embedded SQL execution failed sql=%r parameter_types=%s parameter_count=%d",
                _statement_summary(sql),
                [type(value).__name__ for value in params],
                len(params),
            )
            raise
        self._rows = iter(result)
        statement = sql.lstrip().partition(" ")[0].upper()
        self.rowcount = -1 if statement in {"SELECT", "WITH"} else 1

    def fetchone(self) -> Any | None:
        try:
            return next(self._rows)
        except (StopIteration, EOFError):
            return None

    def fetchall(self) -> list[Any]:
        rows: list[Any] = []
        while True:
            row = self.fetchone()
            if row is None:
                return rows
            rows.append(row)

    def close(self) -> None:
        self._rows = iter(())


class EmbeddedIrisConnection:
    def __init__(self) -> None:
        self._transaction_started = False
        self._closed = False

    def _ensure_transaction(self) -> None:
        if self._closed:
            raise RuntimeError("connection is closed")
        if not self._transaction_started:
            _embedded_iris().tstart()
            self._transaction_started = True

    def cursor(self) -> EmbeddedIrisCursor:
        if self._closed:
            raise RuntimeError("connection is closed")
        return EmbeddedIrisCursor(self)

    def commit(self) -> None:
        if self._transaction_started:
            _embedded_iris().tcommit()
            self._transaction_started = False

    def rollback(self) -> None:
        if self._transaction_started:
            _embedded_iris().trollbackone()
            self._transaction_started = False

    def close(self) -> None:
        self.rollback()
        self._closed = True


class IrisConnectionFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self) -> Any:
        iris = import_module("iris")

        if hasattr(iris, "sql"):
            return EmbeddedIrisConnection()

        dbapi = import_module("iris.dbapi")

        connection = dbapi.connect(
            hostname=self.settings.iris_host,
            port=self.settings.iris_port,
            namespace=self.settings.iris_namespace,
            username=self.settings.iris_username,
            password=self.settings.iris_password,
        )
        connection.autocommit = False
        return connection

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()
