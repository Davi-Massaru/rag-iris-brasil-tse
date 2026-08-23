from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings
from app.domain import utc_now
from app.ingestion.http import ExternalContractError, HttpClient

from .contracts import TseDataset, TseResource

TSE_HOSTS = {"dadosabertos.tse.jus.br", "cdn.tse.jus.br"}


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    path: Path
    sha256: str
    collected_at: datetime


class TseClient:
    def __init__(self, settings: Settings, http: HttpClient) -> None:
        self.settings = settings
        self.http = http

    def dataset(self) -> TseDataset:
        payload = self.http.get_json(
            f"{self.settings.tse_ckan_base_url.rstrip('/')}/package_show",
            params={"id": self.settings.tse_dataset_id},
            allowed_hosts=TSE_HOSTS,
        )
        if payload.get("success") is not True:
            raise ExternalContractError("TSE CKAN returned success=false")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("name") != self.settings.tse_dataset_id:
            raise ExternalContractError("unexpected TSE dataset")
        try:
            return TseDataset.model_validate(result)
        except ValidationError as exc:
            raise ExternalContractError("invalid TSE dataset contract") from exc

    def candidate_resource(self, dataset: TseDataset) -> TseResource:
        matches = [
            item
            for item in dataset.resources
            if item.name.casefold() == "candidatos"
            and item.format.upper() == "CSV"
            and item.state == "active"
        ]
        if len(matches) != 1:
            raise ExternalContractError(f"expected one candidate resource, found {len(matches)}")
        self._validate_resource(matches[0])
        return matches[0]

    def proposal_resources(self, dataset: TseDataset, states: tuple[str, ...]) -> list[TseResource]:
        prefixes = {"BR", *states}
        matches = [
            item
            for item in dataset.resources
            if item.name.split(" - ", 1)[0].upper() in prefixes
            and item.name.casefold().endswith(" - proposta de governo")
            and item.format.upper() == "PDF"
            and item.state == "active"
        ]
        for resource in matches:
            self._validate_resource(resource)
        return matches

    def download(self, resource: TseResource, destination: Path) -> DownloadedArtifact:
        self._validate_resource(resource)
        response = self.http.get(resource.url, allowed_hosts=TSE_HOSTS, stream=True)
        digest = hashlib.sha256()
        try:
            with destination.open("wb") as output:
                for chunk in self.http.chunks(response):
                    digest.update(chunk)
                    output.write(chunk)
        finally:
            response.close()
        return DownloadedArtifact(destination, digest.hexdigest(), utc_now())

    @staticmethod
    def _validate_resource(resource: TseResource) -> None:
        if resource.state != "active":
            raise ExternalContractError("inactive TSE resource")
        HttpClient._validate_url(resource.url, TSE_HOSTS)
