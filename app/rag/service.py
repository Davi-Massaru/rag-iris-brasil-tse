from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from openai import OpenAI

from app.domain import Candidate, SearchResult
from app.retrieval import QueryStrategy, plan_query

from .prompt import POLICY, build_prompt

LOGGER = logging.getLogger(__name__)

NO_EVIDENCE = (
    "Não foram encontradas evidências suficientes nas fontes indexadas "
    "para responder a esta pergunta."
)
NO_CANDIDATE = "Selecione um candidato para realizar esta consulta."


class LanguageModel(Protocol):
    def generate(self, instructions: str, prompt: str, /) -> str: ...


class Retrieval(Protocol):
    def search(
        self,
        query: str,
        candidate_id: int | None = None,
        source_type: str | None = None,
        top_k: int = 8,
    ) -> list[SearchResult]: ...


class CandidateLookup(Protocol):
    def find_by_id(self, candidate_id: int) -> Candidate | None: ...


class OpenAILanguageModel:
    def __init__(self, api_key: str | None, model: str, max_output_tokens: int = 1_800) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def generate(self, instructions: str, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=prompt,
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        return response.output_text.strip()


@dataclass(frozen=True, slots=True)
class RagAnswer:
    answer: str
    sources: tuple[dict, ...]
    candidate: dict | None = None
    query_intent: str | None = None

    def as_dict(self) -> dict:
        return {
            "answer": self.answer,
            "sources": list(self.sources),
            "candidate": self.candidate,
            "queryIntent": self.query_intent,
        }


class RagService:
    def __init__(
        self,
        retrieval: Retrieval,
        language_model: LanguageModel,
        candidates: CandidateLookup | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.language_model = language_model
        self.candidates = candidates

    def ask(self, question: str, candidate_id: int | None = None) -> RagAnswer:
        started = perf_counter()
        plan = plan_query(question)
        candidate = self._candidate(candidate_id)
        candidate_data = _candidate_source(candidate)
        if candidate_id is None and plan.strategy in {
            QueryStrategy.DOCUMENT_COVERAGE,
            QueryStrategy.THEME_FREQUENCY,
        }:
            return RagAnswer(NO_CANDIDATE, (), None, plan.intent)
        top_k = 12 if plan.strategy == QueryStrategy.DOCUMENT_COVERAGE else 8
        retrieval_started = perf_counter()
        retrieved = self.retrieval.search(question, candidate_id=candidate_id, top_k=top_k)
        retrieval_ms = round((perf_counter() - retrieval_started) * 1_000, 2)
        evidence = [
            item
            for item in retrieved
            if _valid_evidence(item) and (candidate is None or item.candidate_id == candidate.id)
        ]
        if not evidence:
            self._log(question, candidate_id, plan.intent, retrieval_ms, 0.0, 0, started)
            return RagAnswer(NO_EVIDENCE, (), candidate_data, plan.intent)
        generation_started = perf_counter()
        answer = self.language_model.generate(
            POLICY,
            build_prompt(question, evidence, candidate, plan.intent),
        )
        generation_ms = round((perf_counter() - generation_started) * 1_000, 2)
        self._log(
            question,
            candidate_id,
            plan.intent,
            retrieval_ms,
            generation_ms,
            len(evidence),
            started,
        )
        return RagAnswer(
            answer,
            _cited_sources(answer, evidence),
            candidate_data,
            plan.intent,
        )

    @staticmethod
    def _log(
        question: str,
        candidate_id: int | None,
        intent: str,
        retrieval_ms: float,
        generation_ms: float,
        chunks: int,
        started: float,
    ) -> None:
        LOGGER.info(
            "rag completed candidate_id=%s intent=%s question=%r retrieval_time_ms=%.2f "
            "generation_time_ms=%.2f total_time_ms=%.2f chunks_retrieved=%d",
            candidate_id,
            intent,
            question,
            retrieval_ms,
            generation_ms,
            (perf_counter() - started) * 1_000,
            chunks,
        )

    def _candidate(self, candidate_id: int | None) -> Candidate | None:
        if candidate_id is None or self.candidates is None:
            return None
        candidate = self.candidates.find_by_id(candidate_id)
        if candidate is None:
            raise LookupError("candidate not found")
        return candidate


def _source(item: SearchResult, evidence_id: str) -> dict:
    return {
        "evidenceId": evidence_id,
        "chunkId": item.chunk_id,
        "candidateId": item.candidate_id,
        "sourceType": item.source_type,
        "sourceId": item.source_id,
        "title": item.title,
        "content": item.content,
        "sourceUrl": item.source_url,
        "score": item.score,
        "metadata": item.metadata,
    }


def _cited_sources(answer: str, evidence: list[SearchResult]) -> tuple[dict, ...]:
    cited = [int(value) for value in re.findall(r"\[E(\d+)\]", answer)]
    positions = list(dict.fromkeys(cited)) or list(range(1, len(evidence) + 1))
    return tuple(
        _source(evidence[position - 1], f"E{position}")
        for position in positions
        if 1 <= position <= len(evidence)
    )


def _valid_evidence(item: SearchResult) -> bool:
    text = item.content.strip()
    if not text:
        return False
    if "%Stream.GlobalCharacter" in text or "^IRISPoliti" in text:
        return False
    return not any(ord(char) < 32 and char not in "\n\r\t" for char in text)


def _candidate_source(candidate: Candidate | None) -> dict | None:
    if candidate is None:
        return None
    return {
        "id": candidate.id,
        "name": candidate.name,
        "ballotName": candidate.ballot_name,
        "party": candidate.party,
        "office": candidate.office,
        "state": candidate.state,
        "tseId": candidate.tse_id,
    }
