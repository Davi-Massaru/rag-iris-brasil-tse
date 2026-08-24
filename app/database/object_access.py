from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from importlib import import_module
from typing import Any

IRIS_DATE_EPOCH = date(1840, 12, 31)
_CLASS_PATHS = {
    "Candidate": ("IRISPolitical", "Model", "Candidate"),
    "IngestionRun": ("IRISPolitical", "Model", "IngestionRun"),
}


def embedded_value(value: Any) -> Any:
    """Convert Python values to the logical representation expected by Embedded IRIS."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="microseconds")
    if isinstance(value, date):
        return (value - IRIS_DATE_EPOCH).days
    return value


class EmbeddedObjectAccess:
    """Small, allow-listed gateway to IRIS persistent objects."""

    def __init__(
        self,
        ensure_transaction: Callable[[], None],
        module_loader: Callable[[], Any] | None = None,
    ) -> None:
        self._ensure_transaction = ensure_transaction
        self._module_loader = module_loader or (lambda: import_module("iris"))

    def open_id(
        self,
        class_name: str,
        object_id: int,
        *,
        for_update: bool = False,
    ) -> Any | None:
        iris_class = self._class(class_name)
        if for_update:
            self._ensure_transaction()
            value = iris_class._OpenId(str(object_id), 4)
        else:
            value = iris_class._OpenId(str(object_id))
        if isinstance(value, str) and value == "":
            return None
        return value

    def new(self, class_name: str) -> Any:
        return self._class(class_name)._New()

    def set_values(self, target: Any, values: Mapping[str, Any]) -> None:
        for name, value in values.items():
            setattr(target, name, embedded_value(value))

    def save(self, target: Any) -> int:
        self._ensure_transaction()
        iris = self._module_loader()
        iris.check_status(target._Save())
        object_id = target._Id()
        if object_id in (None, ""):
            raise RuntimeError("IRIS object save did not return an ID")
        return int(object_id)

    def _class(self, class_name: str) -> Any:
        try:
            path = _CLASS_PATHS[class_name]
        except KeyError as exc:
            raise ValueError("IRIS class is not allowed") from exc
        value = self._module_loader()
        for part in path:
            value = getattr(value, part)
        return value
