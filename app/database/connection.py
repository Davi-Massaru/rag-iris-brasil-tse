from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.config import Settings


class IrisConnectionFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def connect(self) -> Any:
        from iris import dbapi  # type: ignore[attr-defined]

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
