from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from typing import Any, Protocol, cast

from app.config import Settings


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


class EmbeddedIrisCursor:
    def __init__(self, connection: EmbeddedIrisConnection) -> None:
        self.connection = connection
        self._rows: Iterator[Any] = iter(())
        self.rowcount = -1

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.connection._ensure_transaction()
        result = _embedded_iris().sql.exec(sql, *params)
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
