from __future__ import annotations

from collections.abc import Iterator
from datetime import date
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

    def search_deputies(self, name: str, state: str) -> tuple[DeputySummary, ...]:
        items = self._collection(
            "/deputados",
            {
                "nome": name,
                "siglaUf": state,
                "dataInicio": self.settings.camara_match_start_date,
                "dataFim": date.today().isoformat(),
                "pagina": 1,
                "itens": self.settings.camara_page_size,
            },
        )
        unique = {int(item["id"]): item for item in items if "id" in item}
        return tuple(self._model(DeputySummary, item) for item in unique.values())

    def deputy(self, deputy_id: int) -> DeputyDetail:
        return self._model(DeputyDetail, self._entity(f"/deputados/{deputy_id}"))

    def history(self, deputy_id: int) -> tuple[HistoryItem, ...]:
        return tuple(
            self._model(HistoryItem, item)
            for item in self._collection(f"/deputados/{deputy_id}/historico")
        )

    def external_mandates(self, deputy_id: int) -> tuple[ExternalMandate, ...]:
        return tuple(
            self._model(ExternalMandate, item)
            for item in self._collection(f"/deputados/{deputy_id}/mandatosExternos")
        )

    def propositions(self, deputy_id: int) -> Iterator[PropositionSummary]:
        params = {
            "idDeputadoAutor": deputy_id,
            "pagina": 1,
            "itens": self.settings.camara_page_size,
            "ordem": "ASC",
            "ordenarPor": "id",
        }
        yield from (
            self._model(PropositionSummary, item)
            for item in self._collection("/proposicoes", params)
        )

    def proposition(self, proposition_id: int) -> PropositionDetail:
        return self._model(PropositionDetail, self._entity(f"/proposicoes/{proposition_id}"))

    def authors(self, proposition_id: int) -> tuple[PropositionAuthor, ...]:
        return tuple(
            self._model(PropositionAuthor, item)
            for item in self._collection(f"/proposicoes/{proposition_id}/autores")
        )

    def topics(self, proposition_id: int) -> tuple[PropositionTopic, ...]:
        return tuple(
            self._model(PropositionTopic, item)
            for item in self._collection(f"/proposicoes/{proposition_id}/temas")
        )

    def _collection(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        url = path if path.startswith("https://") else f"{self.base_url}{path}"
        items: list[dict[str, Any]] = []
        current_params = params
        while url:
            payload = self.http.get_json(url, params=current_params, allowed_hosts=CAMARA_HOSTS)
            envelope = self._model(CollectionEnvelope, payload)
            items.extend(envelope.dados)
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
