from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.ingestion.http import ExternalContractError, HttpClient

from .contracts import (
    CollectionEnvelope,
    DeputyDetail,
    DeputySummary,
    EntityEnvelope,
    ExternalMandate,
    HistoryItem,
    PropositionAuthor,
    PropositionDetail,
    PropositionSummary,
    PropositionTopic,
)
from .pagination import next_url

CAMARA_HOSTS = {"dadosabertos.camara.leg.br"}
T = TypeVar("T", bound=BaseModel)


class CamaraClient:
    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http
        self.base_url = settings.camara_base_url.rstrip("/")
        self._deputies_by_state: dict[str, tuple[DeputySummary, ...]] = {}
        self._deputy_details: dict[int, DeputyDetail] = {}
        self._history_by_deputy: dict[int, tuple[HistoryItem, ...]] = {}

    @property
    def lookback_start(self) -> date:
        today = date.today()
        try:
            return today.replace(year=today.year - self.settings.camara_lookback_years)
        except ValueError:
            return today.replace(
                year=today.year - self.settings.camara_lookback_years,
                day=28,
            )

    def search_deputies(self, name: str, state: str) -> tuple[DeputySummary, ...]:
        summaries = self._state_deputies(state)
        target = _name_terms(name)
        if not target:
            return ()
        exact = tuple(
            item for item in summaries if _normalize_name(item.nome) == _normalize_name(name)
        )
        if exact:
            return exact
        return tuple(item for item in summaries if _compatible_name_terms(target, item.nome))

    def _state_deputies(self, state: str) -> tuple[DeputySummary, ...]:
        cached = self._deputies_by_state.get(state)
        if cached is not None:
            return cached
        items = self._collection(
            "/deputados",
            {
                "siglaUf": state,
                "dataInicio": self.lookback_start.isoformat(),
                "dataFim": date.today().isoformat(),
                "pagina": 1,
                "itens": self.settings.camara_page_size,
            },
        )
        unique = {int(item["id"]): item for item in items if "id" in item}
        result = tuple(self._model(DeputySummary, item) for item in unique.values())
        self._deputies_by_state[state] = result
        return result

    def deputy(self, deputy_id: int) -> DeputyDetail:
        cached = self._deputy_details.get(deputy_id)
        if cached is None:
            cached = self._model(DeputyDetail, self._entity(f"/deputados/{deputy_id}"))
            self._deputy_details[deputy_id] = cached
        return cached

    def history(self, deputy_id: int) -> tuple[HistoryItem, ...]:
        cached = self._history_by_deputy.get(deputy_id)
        if cached is None:
            cached = tuple(
                self._model(HistoryItem, item)
                for item in self._collection(f"/deputados/{deputy_id}/historico")
            )
            self._history_by_deputy[deputy_id] = cached
        return cached

    def external_mandates(self, deputy_id: int) -> tuple[ExternalMandate, ...]:
        return tuple(
            self._model(ExternalMandate, item)
            for item in self._collection(f"/deputados/{deputy_id}/mandatosExternos")
        )

    def propositions(self, deputy_id: int) -> Iterator[PropositionSummary]:
        remaining = self.settings.camara_max_propositions_per_candidate
        seen: set[int] = set()
        window_end = date.today()
        while remaining and window_end >= self.lookback_start:
            window_start = max(
                self.lookback_start,
                _subtract_months(window_end, 3) + timedelta(days=1),
            )
            params = {
                "idDeputadoAutor": deputy_id,
                "dataInicio": window_start.isoformat(),
                "dataFim": window_end.isoformat(),
                "pagina": 1,
                "itens": self.settings.camara_page_size,
                "ordem": "DESC",
                "ordenarPor": "id",
            }
            for item in self._collection("/proposicoes", params, limit=remaining):
                summary = self._model(PropositionSummary, item)
                if summary.id in seen:
                    continue
                seen.add(summary.id)
                remaining -= 1
                yield summary
                if not remaining:
                    return
            window_end = window_start - timedelta(days=1)

    def proposition(self, proposition_id: int) -> PropositionDetail:
        return self._model(PropositionDetail, self._entity(f"/proposicoes/{proposition_id}"))

    def authors(self, proposition_id: int) -> tuple[PropositionAuthor, ...]:
        authors = tuple(
            self._model(PropositionAuthor, item)
            for item in self._collection(f"/proposicoes/{proposition_id}/autores")
        )
        prioritized = sorted(authors, key=lambda item: item.proponente not in (1, True))
        return tuple(prioritized[: self.settings.camara_max_authors_per_proposition])

    def topics(self, proposition_id: int) -> tuple[PropositionTopic, ...]:
        return tuple(
            self._model(PropositionTopic, item)
            for item in self._collection(f"/proposicoes/{proposition_id}/temas")
        )

    def _collection(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        url = path if path.startswith("https://") else f"{self.base_url}{path}"
        items: list[dict[str, Any]] = []
        current_params = params
        while url:
            payload = self.http.get_json(url, params=current_params, allowed_hosts=CAMARA_HOSTS)
            envelope = self._model(CollectionEnvelope, payload)
            items.extend(envelope.dados)
            if limit is not None and len(items) >= limit:
                return items[:limit]
            url = next_url(envelope.links) or ""
            current_params = None
        return items

    def _entity(self, path: str) -> dict[str, Any]:
        payload = self.http.get_json(f"{self.base_url}{path}", allowed_hosts=CAMARA_HOSTS)
        return self._model(EntityEnvelope, payload).dados

    @staticmethod
    def _model(model: type[T], value: Any) -> T:
        try:
            return model.model_validate(value)
        except ValidationError as exc:
            raise ExternalContractError(f"invalid Câmara {model.__name__} contract") from exc


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", without_marks.upper()).strip()


def _name_terms(value: str) -> set[str]:
    particles = {"DA", "DAS", "DE", "DO", "DOS", "E"}
    return {term for term in _normalize_name(value).split() if term not in particles}


def _compatible_name_terms(target: set[str], candidate_name: str) -> bool:
    candidate = _name_terms(candidate_name)
    if len(target) == 1 or len(candidate) == 1:
        return target == candidate
    return target <= candidate or candidate <= target
