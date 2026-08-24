from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from openai import OpenAI

from app.domain import Candidate, SearchResult
from app.retrieval import QueryStrategy, plan_query

from .context import EnrichedEvidence, RagContext
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


class ContextLoader(Protocol):
    def load(
        self,
        selected_candidate: Candidate | None,
        evidence: Sequence[SearchResult],
    ) -> RagContext: ...


class OpenAILanguageModel:
    def __init__(self, api_key: str | None, model: str, max_output_tokens: int = 4_000) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def generate(self, instructions: str, prompt: str) -> str:
        response = self._create(instructions, prompt, self.max_output_tokens)
        answer = response.output_text.strip()
        if answer and response.status != "incomplete":
            return answer

        reason = getattr(response.incomplete_details, "reason", None)
        LOGGER.warning(
            "model response incomplete or empty status=%s reason=%s output_length=%d; retrying",
            response.status,
            reason,
            len(answer),
        )
        retry_limit = min(max(self.max_output_tokens * 2, 4_000), 8_000)
        response = self._create(
            instructions
            + "\nA resposta anterior ficou incompleta. Entregue agora uma síntese final curta, "
            "com no máximo 500 palavras e citações das evidências.",
            prompt,
            retry_limit,
        )
        answer = response.output_text.strip()
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None)
            LOGGER.error(
                "model retry remained incomplete reason=%s output_length=%d",
                reason,
                len(answer),
            )
            return ""
        return answer

    def _create(self, instructions: str, prompt: str, max_output_tokens: int):  # noqa: ANN202
        return self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=prompt,
            max_output_tokens=max_output_tokens,
            store=False,
        )


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
        context_loader: ContextLoader | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.language_model = language_model
        self.candidates = candidates
        self.context_loader = context_loader

    def ask(self, question: str, candidate_id: int | None = None) -> RagAnswer:
        started = perf_counter()
        plan = plan_query(question)
        candidate = self._candidate(candidate_id)
        candidate_data = _candidate_source(candidate)
        top_k = _retrieval_limit(candidate, plan.strategy)
        retrieval_started = perf_counter()
        retrieved = self.retrieval.search(question, candidate_id=candidate_id, top_k=top_k)
        retrieval_ms = round((perf_counter() - retrieval_started) * 1_000, 2)
        evidence = [
            item
            for item in retrieved
            if _valid_evidence(item) and (candidate is None or item.candidate_id == candidate.id)
        ]
        if candidate is None:
            evidence = _diversify_by_candidate(evidence, total=12, per_candidate=3)
        if not evidence:
            self._log(question, candidate_id, plan.intent, retrieval_ms, 0.0, 0, started)
            if candidate is not None and not retrieved:
                return RagAnswer(
                    _candidate_profile(candidate),
                    (),
                    candidate_data,
                    plan.intent,
                )
            return RagAnswer(NO_EVIDENCE, (), candidate_data, plan.intent)
        generation_started = perf_counter()
        context = self._context(candidate, evidence)
        answer = self.language_model.generate(
            POLICY,
            build_prompt(question, context, plan.intent),
        ).strip()
        if not answer:
            LOGGER.error("model returned no complete text; using evidence summary")
            answer = _evidence_summary(context)
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

    def _context(
        self,
        candidate: Candidate | None,
        evidence: Sequence[SearchResult],
    ) -> RagContext:
        if self.context_loader is not None:
            return self.context_loader.load(candidate, evidence)
        if candidate is None:
            raise RuntimeError("context loader is required for candidate discovery")
        return RagContext(
            "INDIVIDUAL",
            candidate,
            tuple(EnrichedEvidence(candidate, item, {}) for item in evidence),
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
        "partyNumber": candidate.party_number,
        "office": candidate.office,
        "state": candidate.state,
        "candidateNumber": candidate.candidate_number,
        "tseId": candidate.tse_id,
    }


def _candidate_profile(candidate: Candidate) -> str:
    identity = candidate.ballot_name or candidate.name
    details = [candidate.office, candidate.state]
    if candidate.party:
        party = candidate.party
        if candidate.party_number is not None:
            party += f" ({candidate.party_number})"
        details.append(party)
    if candidate.candidate_number is not None:
        details.append(f"número {candidate.candidate_number}")
    return (
        f"### {identity}\n\n"
        f"**Nome completo:** {candidate.name}\n\n"
        f"**Cadastro eleitoral:** {' · '.join(details)}.\n\n"
        "Não há propostas, proposições ou histórico político indexados para este candidato. "
        "Por isso, o resumo disponível está limitado aos dados cadastrais do TSE."
    )


def _retrieval_limit(candidate: Candidate | None, strategy: QueryStrategy) -> int:
    if candidate is None:
        return 24
    return 12 if strategy == QueryStrategy.DOCUMENT_COVERAGE else 8


def _diversify_by_candidate(
    evidence: Sequence[SearchResult],
    total: int,
    per_candidate: int,
) -> list[SearchResult]:
    counts: dict[int, int] = {}
    selected: list[SearchResult] = []
    for item in evidence:
        if counts.get(item.candidate_id, 0) >= per_candidate:
            continue
        selected.append(item)
        counts[item.candidate_id] = counts.get(item.candidate_id, 0) + 1
        if len(selected) >= total:
            break
    return selected


def _evidence_summary(context: RagContext) -> str:
    lines = [
        "Não foi possível concluir a síntese do modelo. "
        "Abaixo estão os resultados diretamente sustentados pelas evidências recuperadas:"
    ]
    current_candidate: int | None = None
    for index, item in enumerate(context.evidence, 1):
        candidate = item.candidate
        if candidate.id != current_candidate:
            identity = candidate.ballot_name or candidate.name
            details = " / ".join(
                value for value in (candidate.party, candidate.office, candidate.state) if value
            )
            lines.extend(("", f"### {identity}" + (f" — {details}" if details else "")))
            current_candidate = candidate.id
        summary = _evidence_text(item)
        lines.append(f"- **{item.chunk.title or item.chunk.source_type}:** {summary} [E{index}]")
    return "\n".join(lines)


def _evidence_text(item: EnrichedEvidence, limit: int = 320) -> str:
    structured = item.source_data
    values = [
        structured.get("summary"),
        structured.get("detailedSummary"),
        structured.get("situation"),
        item.chunk.content,
    ]
    text = next((str(value) for value in values if value), "Evidência relacionada localizada.")
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    shortened = normalized[: limit - 1].rsplit(" ", 1)[0]
    return f"{shortened}…"
