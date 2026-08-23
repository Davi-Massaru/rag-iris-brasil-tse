from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TseResource(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    id: str
    name: str
    format: str
    mimetype: str | None = None
    url: str
    state: str


class TseDataset(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    id: str
    name: str
    title: str
    metadata_modified: str | None = None
    resources: tuple[TseResource, ...]


class TseCandidateRaw(BaseModel):
    model_config = ConfigDict(frozen=True)
    election_year: int
    state: str
    office_code: int | None
    office_name: str
    candidate_sequence: str
    candidate_number: int | None
    candidate_name: str
    ballot_name: str | None
    party_number: int | None
    party_abbreviation: str | None
