from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain import Candidate, MatchStatus
from app.ingestion.camara.contracts import (
    DeputyDetail,
    DeputyStatus,
    DeputySummary,
    HistoryItem,
)
from app.ingestion.matching import CandidateMatcher
from app.ingestion.matching.candidate_matcher import normalize_name

pytestmark = pytest.mark.unit


class CamaraStub:
    def __init__(self, detail: DeputyDetail, parties: tuple[str, ...] = ("ABC",)) -> None:
        self.detail = detail
        self.parties = parties

    def search_deputies(self, name: str, state: str) -> tuple[DeputySummary, ...]:
        del name, state
        return (DeputySummary(id=self.detail.id, uri="https://official", nome="JOAO"),)

    def deputy(self, deputy_id: int) -> DeputyDetail:
        del deputy_id
        return self.detail

    def history(self, deputy_id: int) -> tuple[HistoryItem, ...]:
        del deputy_id
        return tuple(HistoryItem(siglaPartido=party) for party in self.parties)


def candidate() -> Candidate:
    return Candidate(
        id=1,
        tse_id="TSE1",
        name="João da Silva",
        ballot_name="João Silva",
        party="ABC",
        office="DEPUTADO FEDERAL",
        state="SP",
        candidate_number=1010,
        party_number=10,
    )


def detail(civil_name: str = "JOAO DA SILVA", state: str = "SP") -> DeputyDetail:
    return DeputyDetail(
        id=99,
        nomeCivil=civil_name,
        ultimoStatus=DeputyStatus(nome="JOÃO SILVA", nomeEleitoral="JOÃO SILVA", siglaUf=state),
    )


def test_name_normalization_removes_accents_and_punctuation() -> None:
    assert normalize_name("João d'Ávila") == "JOAO D AVILA"


def test_exact_evidence_produces_match() -> None:
    result = CandidateMatcher(CamaraStub(detail())).match(candidate())

    assert result.status == MatchStatus.MATCHED
    assert result.deputy_id == 99
    assert result.confidence == 100


def test_review_does_not_persist_deputy_id() -> None:
    review_candidate = replace(candidate(), ballot_name="NOME DIFERENTE", party="XYZ")
    result = CandidateMatcher(CamaraStub(detail())).match(review_candidate)

    assert result.status == MatchStatus.REVIEW
    assert result.deputy_id is None
    assert result.confidence == 75
