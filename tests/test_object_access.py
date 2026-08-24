from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.database.object_access import EmbeddedObjectAccess

pytestmark = pytest.mark.unit


class PersistentObject:
    def __init__(self, object_id: str = "41", status: int = 1) -> None:
        self.object_id = object_id
        self.status = status

    def _Save(self) -> int:
        return self.status

    def _Id(self) -> str:
        return self.object_id


class PersistentClass:
    def __init__(self) -> None:
        self.existing = PersistentObject()
        self.open_calls: list[tuple] = []

    def _OpenId(self, *args):  # noqa: ANN002, ANN201, N802
        self.open_calls.append(args)
        return self.existing if args[0] == "41" else ""

    def _New(self) -> PersistentObject:  # noqa: N802
        return PersistentObject("42")


def iris_module(candidate: PersistentClass, checked: list[int]) -> SimpleNamespace:
    return SimpleNamespace(
        IRISPolitical=SimpleNamespace(Model=SimpleNamespace(Candidate=candidate)),
        check_status=checked.append,
    )


def test_object_access_normalizes_missing_id_and_uses_write_concurrency() -> None:
    candidate = PersistentClass()
    transactions: list[str] = []
    module = iris_module(candidate, [])
    access = EmbeddedObjectAccess(lambda: transactions.append("transaction"), lambda: module)

    assert access.open_id("Candidate", 999) is None
    assert transactions == []

    value = access.open_id("Candidate", 41, for_update=True)

    assert value is candidate.existing
    assert candidate.open_calls[-1] == ("41", 4)
    assert transactions == ["transaction"]


def test_object_access_normalizes_values_checks_status_and_returns_integer_id() -> None:
    candidate = PersistentClass()
    checked: list[int] = []
    transactions: list[str] = []
    module = iris_module(candidate, checked)
    access = EmbeddedObjectAccess(lambda: transactions.append("transaction"), lambda: module)
    target = access.new("Candidate")

    access.set_values(
        target,
        {
            "Optional": None,
            "Timestamp": datetime(2026, 8, 24, 20, 1, 2, 3456),
            "EventDate": date(2026, 8, 24),
        },
    )
    object_id = access.save(target)

    assert target.Optional == ""
    assert target.Timestamp == "2026-08-24 20:01:02.003456"
    assert target.EventDate == 67806
    assert checked == [1]
    assert transactions == ["transaction"]
    assert object_id == 42


def test_object_access_rejects_unapproved_class() -> None:
    access = EmbeddedObjectAccess(lambda: None, lambda: SimpleNamespace())

    with pytest.raises(ValueError, match="not allowed"):
        access.new("Unapproved")
