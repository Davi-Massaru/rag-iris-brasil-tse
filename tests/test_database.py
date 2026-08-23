from __future__ import annotations

import pytest

from app.database import transaction

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
