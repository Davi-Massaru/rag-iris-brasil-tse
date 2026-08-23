from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any


class MatchStatus(StrEnum):
    MATCHED = "MATCHED"
    REVIEW = "REVIEW"
    UNMATCHED = "UNMATCHED"


@dataclass(frozen=True, slots=True)
class UpsertResult:
    id: int
    action: str


@dataclass(frozen=True, slots=True)
class CandidateWrite:
    tse_id: str
    name: str
    ballot_name: str | None
    party: str | None
    party_number: int | None
    office: str
    state: str
    candidate_number: int | None
    source_url: str
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    id: int
    tse_id: str
    name: str
    ballot_name: str | None
    party: str | None
    party_number: int | None
    office: str
    state: str
    candidate_number: int | None
    camara_deputy_id: int | None = None
    match_status: str | None = None
    match_confidence: float | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryWrite:
    candidate_id: int
    institution: str
    position: str | None
    party: str | None
    state: str | None
    start_date: date | None
    end_date: date | None
    external_id: str
    situation: str | None
    source_url: str
    collected_at: datetime
    raw_json: str


@dataclass(frozen=True, slots=True)
class PropositionWrite:
    candidate_id: int
    camara_id: int
    type: str | None
    number: int | None
    year: int | None
    title: str
    summary: str | None
    detailed_summary: str | None
    presentation_date: date | None
    status: str | None
    source_url: str
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorWrite:
    proposition_id: int
    camara_author_id: int | None
    name: str
    author_type: str | None
    uri: str | None
    is_main_author: bool


@dataclass(frozen=True, slots=True)
class TopicWrite:
    proposition_id: int
    external_code: int | None
    name: str


@dataclass(frozen=True, slots=True)
class ProposalDocumentWrite:
    candidate_id: int
    election_year: int
    title: str
    source_url: str
    resource_id: str
    file_name: str
    document_hash: str
    raw_text: str
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class ChunkWrite:
    candidate_id: int
    source_type: str
    source_id: str
    chunk_index: int
    title: str
    content: str
    source_url: str
    metadata_json: str
    content_hash: str
    token_count: int
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class Chunk:
    id: int
    candidate_id: int
    source_type: str
    source_id: str
    title: str
    content: str
    source_url: str
    metadata_json: str = "{}"
    token_count: int = 0


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: int
    candidate_id: int
    source_type: str
    source_id: str
    title: str
    content: str
    source_url: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MatchResult:
    deputy_id: int | None
    status: MatchStatus
    confidence: float


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
