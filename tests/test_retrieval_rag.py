from __future__ import annotations

import pytest

from app.domain import SearchResult
from app.ingestion.chunking import TokenChunker
from app.ingestion.chunking.chunker import content_hash, normalize_content
from app.rag import NO_EVIDENCE, RagService
from app.rag.prompt import build_prompt
from app.retrieval.rrf import reciprocal_rank_fusion

pytestmark = pytest.mark.unit


class WordEncoding:
    def __init__(self) -> None:
        self.words: list[str] = []

    def encode(self, text: str) -> list[int]:
        self.words = text.split()
        return list(range(len(self.words)))

    def decode(self, tokens) -> str:  # noqa: ANN001
        return " ".join(self.words[index] for index in tokens)


def result(chunk_id: int, score: float = 1.0) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        candidate_id=7,
        source_type="PROPOSITION",
        source_id=str(chunk_id),
        title=f"Título {chunk_id}",
        content="educação pública",
        source_url="https://dadosabertos.camara.leg.br/fonte",
        score=score,
    )


def test_chunking_has_overlap_and_stable_hash() -> None:
    chunker = TokenChunker("text-embedding-3-small", size=8, overlap=2, encoding=WordEncoding())
    chunks = chunker.split("um  dois três quatro cinco seis sete oito nove dez onze doze")

    assert len(chunks) >= 2
    assert content_hash(" texto  igual\r\n") == content_hash("texto igual\n")
    assert normalize_content("a   b") == "a b"


def test_rrf_combines_rankings_deterministically() -> None:
    fused = reciprocal_rank_fusion(([result(1), result(2)], [result(2), result(3)]), 3)

    assert [item.chunk_id for item in fused] == [2, 1, 3]
    assert fused[0].score > fused[1].score


def test_prompt_labels_each_evidence_and_keeps_source() -> None:
    prompt = build_prompt("O que foi proposto?", [result(1), result(2)])

    assert "[E1]" in prompt and "[E2]" in prompt
    assert "https://dadosabertos.camara.leg.br/fonte" in prompt


class EmptyRetrieval:
    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        return []


class ForbiddenModel:
    def generate(self, _instructions: str, _prompt: str) -> str:
        raise AssertionError("LLM must not be called without evidence")


def test_rag_does_not_call_llm_without_evidence() -> None:
    answer = RagService(EmptyRetrieval(), ForbiddenModel()).ask("pergunta")

    assert answer.answer == NO_EVIDENCE
    assert answer.sources == ()
