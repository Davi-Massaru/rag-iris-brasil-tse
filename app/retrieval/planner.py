from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class QueryStrategy(StrEnum):
    HYBRID = "HYBRID"
    DOCUMENT_COVERAGE = "DOCUMENT_COVERAGE"
    THEME_FREQUENCY = "THEME_FREQUENCY"


@dataclass(frozen=True, slots=True)
class QueryPlan:
    intent: str
    strategy: QueryStrategy
    source_type: str | None = None


SOURCE_ALIASES = {
    "PROPOSITION": "PROPOSITION",
    "PROPOSICAO": "PROPOSITION",
    "GOVERNMENT_PROPOSAL": "GOVERNMENT_PROPOSAL",
    "PROPOSTA_GOVERNO": "GOVERNMENT_PROPOSAL",
    "POLITICAL_HISTORY": "POLITICAL_HISTORY",
    "HISTORICO_POLITICO": "POLITICAL_HISTORY",
}


def plan_query(query: str, explicit_source_type: str | None = None) -> QueryPlan:
    if explicit_source_type:
        source_type = SOURCE_ALIASES.get(_normalize(explicit_source_type).replace(" ", "_"))
        if source_type is None:
            raise ValueError("unsupported sourceType")
        return QueryPlan("EXPLICIT_SOURCE", QueryStrategy.HYBRID, source_type)

    normalized = _normalize(query)
    government = _contains_any(
        normalized,
        "plano de governo",
        "programa de governo",
        "proposta de governo",
        "diretrizes de governo",
    )
    summary = _contains_any(normalized, "resumo", "resuma", "sintese", "visao geral")
    if government and summary:
        return QueryPlan(
            "GOVERNMENT_PLAN_SUMMARY",
            QueryStrategy.DOCUMENT_COVERAGE,
            "GOVERNMENT_PROPOSAL",
        )

    frequency = _contains_any(
        normalized,
        "mais frequentes",
        "maior frequencia",
        "aparecem com frequencia",
        "principais temas",
        "temas recorrentes",
        "assuntos recorrentes",
    )
    if frequency:
        return QueryPlan(
            "PROPOSITION_THEME_FREQUENCY",
            QueryStrategy.THEME_FREQUENCY,
            "PROPOSITION",
        )
    if government:
        return QueryPlan("GOVERNMENT_PLAN_TOPIC", QueryStrategy.HYBRID, "GOVERNMENT_PROPOSAL")
    if _contains_any(normalized, "historico politico", "historico parlamentar", "mandato"):
        return QueryPlan("POLITICAL_HISTORY", QueryStrategy.HYBRID, "POLITICAL_HISTORY")
    if _contains_any(normalized, "projeto", "proposicao", "proposicoes", "ementa"):
        return QueryPlan("PROPOSITION_SEARCH", QueryStrategy.HYBRID, "PROPOSITION")
    return QueryPlan("GENERAL_EVIDENCE", QueryStrategy.HYBRID)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\W+", " ", plain.upper()).strip()


def _contains_any(value: str, *phrases: str) -> bool:
    return any(_normalize(phrase) in value for phrase in phrases)
