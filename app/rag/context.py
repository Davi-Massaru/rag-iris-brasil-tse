from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain import Candidate, SearchResult


class CandidateContextLookup(Protocol):
    def find_by_ids(self, candidate_ids: Sequence[int]) -> dict[int, Candidate]: ...


class PropositionContextLookup(Protocol):
    def context_by_camara_ids(
        self, candidate_id: int, camara_ids: Sequence[str]
    ) -> dict[str, dict]: ...


class ProposalDocumentContextLookup(Protocol):
    def context_by_hashes(
        self, candidate_id: int, document_hashes: Sequence[str]
    ) -> dict[str, dict]: ...


class PoliticalHistoryContextLookup(Protocol):
    def context_by_external_ids(
        self, candidate_id: int, external_ids: Sequence[str]
    ) -> dict[str, dict]: ...


class PropositionAuthorContextLookup(Protocol):
    def context_by_proposition_ids(
        self, proposition_ids: Sequence[int]
    ) -> dict[int, list[dict]]: ...


class PropositionTopicContextLookup(Protocol):
    def context_by_proposition_ids(
        self, proposition_ids: Sequence[int]
    ) -> dict[int, list[dict]]: ...


@dataclass(frozen=True, slots=True)
class EnrichedEvidence:
    candidate: Candidate
    chunk: SearchResult
    source_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RagContext:
    mode: str
    selected_candidate: Candidate | None
    evidence: tuple[EnrichedEvidence, ...]


class RagContextLoader:
    def __init__(
        self,
        candidates: CandidateContextLookup,
        propositions: PropositionContextLookup,
        proposal_documents: ProposalDocumentContextLookup,
        political_histories: PoliticalHistoryContextLookup,
        proposition_authors: PropositionAuthorContextLookup,
        proposition_topics: PropositionTopicContextLookup,
    ) -> None:
        self.candidates = candidates
        self.propositions = propositions
        self.proposal_documents = proposal_documents
        self.political_histories = political_histories
        self.proposition_authors = proposition_authors
        self.proposition_topics = proposition_topics

    def load(
        self,
        selected_candidate: Candidate | None,
        evidence: Sequence[SearchResult],
    ) -> RagContext:
        candidates = self._load_candidates(selected_candidate, evidence)
        source_data = self._load_source_data(evidence)
        enriched = tuple(
            EnrichedEvidence(
                candidate=self._candidate(candidates, item.candidate_id),
                chunk=item,
                source_data=source_data.get(
                    _source_key(item),
                    {
                        "status": "SOURCE_RECORD_NOT_FOUND",
                        "sourceType": item.source_type,
                        "sourceId": item.source_id,
                    },
                ),
            )
            for item in evidence
        )
        mode = "INDIVIDUAL" if selected_candidate is not None else "DISCOVERY"
        return RagContext(mode, selected_candidate, enriched)

    def _load_candidates(
        self,
        selected_candidate: Candidate | None,
        evidence: Sequence[SearchResult],
    ) -> dict[int, Candidate]:
        candidate_ids = tuple(dict.fromkeys(item.candidate_id for item in evidence))
        candidates = self.candidates.find_by_ids(candidate_ids)
        if selected_candidate is not None:
            candidates[selected_candidate.id] = selected_candidate
        return candidates

    def _load_source_data(
        self,
        evidence: Sequence[SearchResult],
    ) -> dict[tuple[int, str, str], dict[str, Any]]:
        grouped: dict[tuple[int, str], list[str]] = defaultdict(list)
        for item in evidence:
            grouped[(item.candidate_id, item.source_type)].append(item.source_id)

        result: dict[tuple[int, str, str], dict[str, Any]] = {}
        for (candidate_id, source_type), source_ids in grouped.items():
            if source_type == "PROPOSITION":
                values = self.propositions.context_by_camara_ids(candidate_id, source_ids)
                self._attach_proposition_relations(values)
            elif source_type == "GOVERNMENT_PROPOSAL":
                values = self.proposal_documents.context_by_hashes(candidate_id, source_ids)
            elif source_type == "POLITICAL_HISTORY":
                values = self.political_histories.context_by_external_ids(candidate_id, source_ids)
            else:
                values = {}
            for source_id, value in values.items():
                result[(candidate_id, source_type, str(source_id))] = value
        return result

    def _attach_proposition_relations(self, values: dict[str, dict]) -> None:
        proposition_ids = tuple(
            int(value["propositionId"])
            for value in values.values()
            if value.get("propositionId") is not None
        )
        authors = self.proposition_authors.context_by_proposition_ids(proposition_ids)
        topics = self.proposition_topics.context_by_proposition_ids(proposition_ids)
        for value in values.values():
            proposition_id = int(value["propositionId"])
            value["authors"] = authors.get(proposition_id, [])
            value["topics"] = topics.get(proposition_id, [])

    @staticmethod
    def _candidate(candidates: dict[int, Candidate], candidate_id: int) -> Candidate:
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise LookupError(f"candidate context not found: {candidate_id}")
        return candidate


def _source_key(item: SearchResult) -> tuple[int, str, str]:
    return item.candidate_id, item.source_type, item.source_id
