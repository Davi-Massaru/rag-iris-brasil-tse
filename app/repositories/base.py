from __future__ import annotations

from typing import Any


class RepositorySupport:
    def __init__(self, connection: Any, schema: str) -> None:
        if not schema.replace("_", "").isalnum():
            raise ValueError("invalid SQL schema")
        self.connection = connection
        self.schema = schema

    def table(self, name: str) -> str:
        return f"{self.schema}.{name}"

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return tuple(row) if row is not None else None
        finally:
            cursor.close()

    def all(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return [tuple(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return max(cursor.rowcount, 0)
        finally:
            cursor.close()
