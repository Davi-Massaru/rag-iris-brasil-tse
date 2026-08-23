from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def transaction(connection: Any) -> Iterator[Any]:
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    connection.commit()
