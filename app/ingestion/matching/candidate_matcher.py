from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Protocol

from app.domain import Candidate, MatchResult, MatchStatus
from app.ingestion.camara.contracts import DeputyDetail, DeputySummary, HistoryItem


class CandidateDataClient(Protocol):
    def search_deputies(self, name: str, state: str, /) -> tuple[DeputySummary, ...]: ...

    def deputy(self, deputy_id: int, /) -> DeputyDetail: ...

    def history(self, deputy_id: int, /) -> tuple[HistoryItem, ...]: ...


class CandidateMatcher:
    def __init__(self, client: CandidateDataClient, overrides_path: Path | None = None) -> None:
        self.client = client
        self.overrides = _load_overrides(overrides_path)

    def match(self, candidate: Candidate) -> MatchResult:
        override = self.overrides.get(candidate.tse_id)
        if override is not None:
            return MatchResult(override, MatchStatus.MATCHED, 100.0)
        summaries = self.client.search_deputies(
            candidate.ballot_name or candidate.name, candidate.state
        )
        if not summaries:
            summaries = self.client.search_deputies(_short_name(candidate.name), candidate.state)
        scored = [self._score(candidate, self.client.deputy(item.id)) for item in summaries]
        if not scored:
            return MatchResult(None, MatchStatus.UNMATCHED, 0.0)
        score, deputy_id = max(scored, key=lambda item: (item[0], -item[1]))
        status = _status(score)
        return MatchResult(deputy_id if status == MatchStatus.MATCHED else None, status, score)

    def _score(self, candidate: Candidate, deputy: DeputyDetail) -> tuple[float, int]:
        score = 0.0
        status = deputy.ultimoStatus
        if normalize_name(candidate.name) == normalize_name(deputy.nomeCivil):
            score += 60
        ballot_names = {
            normalize_name(value) for value in (status.nome, status.nomeEleitoral) if value
        }
        if candidate.ballot_name and normalize_name(candidate.ballot_name) in ballot_names:
            score += 20
        if candidate.state == status.siglaUf:
            score += 15
        history_parties = {item.siglaPartido for item in self.client.history(deputy.id)}
        if candidate.party and candidate.party in history_parties:
            score += 5
        return score, deputy.id


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", without_marks.upper()).strip()


def _short_name(value: str) -> str:
    terms = normalize_name(value).split()
    return " ".join((terms[0], terms[-1])) if len(terms) > 1 else terms[0]


def _status(score: float) -> MatchStatus:
    if score >= 90:
        return MatchStatus.MATCHED
    if score >= 70:
        return MatchStatus.REVIEW
    return MatchStatus.UNMATCHED


def _load_overrides(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["tse_candidate_id"]): int(item["camara_deputy_id"])
        for item in payload
        if item.get("verified") is True
    }
