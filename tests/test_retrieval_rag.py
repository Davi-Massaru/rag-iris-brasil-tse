from __future__ import annotations

import pytest

from app.domain import Candidate, SearchResult
from app.ingestion.chunking import PoliticalChunkBuilder, TokenChunker
from app.ingestion.chunking.chunker import content_hash, normalize_content
from app.rag import NO_CANDIDATE, NO_EVIDENCE, RagService
from app.rag.prompt import POLICY, build_prompt
from app.retrieval import QueryStrategy, plan_query
from app.retrieval.rrf import reciprocal_rank_fusion
from app.retrieval.structured import _representative_sample

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


def test_document_builder_rejects_an_unmaterialized_iris_stream() -> None:
    chunker = TokenChunker("test", size=8, overlap=2, encoding=WordEncoding())
    builder = PoliticalChunkBuilder(chunker, None, None)  # type: ignore[arg-type]
    row = (
        1,
        7,
        2026,
        "Plano",
        "https://cdn.tse.jus.br/plano.zip",
        "resource",
        "plano.pdf",
        "a" * 64,
        '\x04\x01%Stream.GlobalCharacter"\x01^IRISPolitical',
        None,
    )

    with pytest.raises(ValueError, match="unmaterialized IRIS stream"):
        builder.document(row)


def test_rrf_combines_rankings_deterministically() -> None:
    fused = reciprocal_rank_fusion(([result(1), result(2)], [result(2), result(3)]), 3)

    assert [item.chunk_id for item in fused] == [2, 1, 3]
    assert fused[0].score > fused[1].score


def test_prompt_labels_each_evidence_and_keeps_source() -> None:
    candidate = Candidate(
        id=7,
        tse_id="TSE7",
        name="ENRICO MISASI",
        ballot_name="ENRICO",
        party="MDB",
        party_number=15,
        office="DEPUTADO FEDERAL",
        state="SP",
        candidate_number=1515,
    )
    prompt = build_prompt("O que foi proposto?", [result(1), result(2)], candidate)

    assert "[E1]" in prompt and "[E2]" in prompt
    assert "https://dadosabertos.camara.leg.br/fonte" in prompt
    assert "Nome: ENRICO MISASI" in prompt
    assert "identidade autoritativa" in POLICY


def test_query_planner_uses_sql_and_document_coverage_without_an_llm() -> None:
    summary = plan_query("resumo do plano de governo")
    themes = plan_query("quais são os principais temas das proposições?")
    history = plan_query("resuma o histórico parlamentar")

    assert summary.strategy == QueryStrategy.DOCUMENT_COVERAGE
    assert summary.source_type == "GOVERNMENT_PROPOSAL"
    assert themes.strategy == QueryStrategy.THEME_FREQUENCY
    assert history.source_type == "POLITICAL_HISTORY"


def test_representative_sample_covers_start_middle_and_end() -> None:
    rows = [(index,) for index in range(101)]

    sampled = _representative_sample(rows, 5)

    assert sampled == [(0,), (25,), (50,), (75,), (100,)]


class EmptyRetrieval:
    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        return []


class ForbiddenModel:
    def generate(self, instructions: str, prompt: str) -> str:
        del instructions, prompt
        raise AssertionError("LLM must not be called without evidence")


def test_rag_does_not_call_llm_without_evidence() -> None:
    answer = RagService(EmptyRetrieval(), ForbiddenModel()).ask("pergunta")

    assert answer.answer == NO_EVIDENCE
    assert answer.sources == ()


class ForbiddenRetrieval:
    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        raise AssertionError("retrieval must not run before a required candidate is selected")


def test_candidate_dependent_summary_stops_before_retrieval_or_llm() -> None:
    answer = RagService(ForbiddenRetrieval(), ForbiddenModel()).ask("resumo do plano de governo")

    assert answer.answer == NO_CANDIDATE
    assert answer.sources == ()


class StaticRetrieval:
    def __init__(self, evidence: list[SearchResult]) -> None:
        self.evidence = evidence

    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        return self.evidence


class StaticCandidates:
    candidate = Candidate(
        id=7,
        tse_id="TSE7",
        name="ENRICO MISASI",
        ballot_name="ENRICO",
        party="MDB",
        party_number=15,
        office="DEPUTADO FEDERAL",
        state="SP",
        candidate_number=1515,
    )

    def find_by_id(self, candidate_id: int) -> Candidate | None:
        return self.candidate if candidate_id == 7 else None


class CapturingModel:
    def __init__(self) -> None:
        self.instructions = ""
        self.prompt = ""

    def generate(self, instructions: str, prompt: str) -> str:
        self.instructions = instructions
        self.prompt = prompt
        return "Resposta sobre Enrico [E1]."


def test_rag_keeps_selected_candidate_identity_and_numbered_source() -> None:
    model = CapturingModel()
    answer = RagService(StaticRetrieval([result(1)]), model, StaticCandidates()).ask(
        "Quais projetos deste candidato tratam de educação?",
        7,
    )

    assert "Nome: ENRICO MISASI" in model.prompt
    assert "nunca deduza outra pessoa" in model.instructions
    assert answer.candidate and answer.candidate["name"] == "ENRICO MISASI"
    assert answer.sources[0]["evidenceId"] == "E1"


def test_rag_rejects_serialized_iris_stream_without_calling_llm() -> None:
    invalid = SearchResult(
        chunk_id=99,
        candidate_id=7,
        source_type="GOVERNMENT_PROPOSAL",
        source_id="hash",
        title="Plano",
        content='\x04\x01%Stream.GlobalCharacter"\x01^IRISPolitical',
        source_url="https://cdn.tse.jus.br/fonte.zip",
        score=1.0,
    )
    answer = RagService(StaticRetrieval([invalid]), ForbiddenModel(), StaticCandidates()).ask(
        "O que consta no plano de governo?",
        7,
    )

    assert answer.answer == NO_EVIDENCE
