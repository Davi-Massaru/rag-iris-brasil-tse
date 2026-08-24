from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from app.domain import Candidate, SearchResult
from app.ingestion.chunking import PoliticalChunkBuilder, TokenChunker
from app.ingestion.chunking.chunker import content_hash, normalize_content
from app.rag import (
    NO_EVIDENCE,
    EnrichedEvidence,
    OpenAILanguageModel,
    RagContext,
    RagContextLoader,
    RagService,
)
from app.rag.prompt import POLICY, build_prompt
from app.retrieval import HybridSearch, QueryStrategy, plan_query
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


def result(
    chunk_id: int,
    score: float = 1.0,
    candidate_id: int = 7,
    source_type: str = "PROPOSITION",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        candidate_id=candidate_id,
        source_type=source_type,
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
    context = RagContext(
        "INDIVIDUAL",
        candidate,
        (
            EnrichedEvidence(candidate, result(1), {"camaraId": 1}),
            EnrichedEvidence(candidate, result(2), {"camaraId": 2}),
        ),
    )
    prompt = build_prompt("O que foi proposto?", context)

    assert "[E1]" in prompt and "[E2]" in prompt
    assert "https://dadosabertos.camara.leg.br/fonte" in prompt
    assert "Nome: ENRICO MISASI" in prompt
    assert "identidade autoritativa" in POLICY


def test_query_planner_uses_sql_and_document_coverage_without_an_llm() -> None:
    summary = plan_query("resumo do plano de governo")
    candidate_summary = plan_query("faça um resumo dele")
    themes = plan_query("quais são os principais temas das proposições?")
    history = plan_query("resuma o histórico parlamentar")

    assert summary.strategy == QueryStrategy.DOCUMENT_COVERAGE
    assert summary.source_type == "GOVERNMENT_PROPOSAL"
    assert candidate_summary.intent == "CANDIDATE_SUMMARY"
    assert candidate_summary.strategy == QueryStrategy.DOCUMENT_COVERAGE
    assert candidate_summary.source_type is None
    assert themes.strategy == QueryStrategy.THEME_FREQUENCY
    assert history.strategy == QueryStrategy.DOCUMENT_COVERAGE
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


class StaticRetrieval:
    def __init__(self, evidence: list[SearchResult]) -> None:
        self.evidence = evidence

    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        return self.evidence


class ForbiddenSemanticSearch:
    def search(self, *_args, **_kwargs) -> list[SearchResult]:
        raise AssertionError("semantic search must not run for a candidate summary")


class CapturingCoverage:
    def __init__(self) -> None:
        self.call: tuple[int, str | None, int] | None = None

    def search(
        self,
        candidate_id: int,
        source_type: str | None,
        top_k: int,
    ) -> list[SearchResult]:
        self.call = candidate_id, source_type, top_k
        return [result(1, candidate_id=candidate_id)]


def test_hybrid_uses_all_candidate_chunks_for_a_generic_summary() -> None:
    coverage = CapturingCoverage()
    retrieval = HybridSearch(
        ForbiddenSemanticSearch(),  # type: ignore[arg-type]
        ForbiddenSemanticSearch(),  # type: ignore[arg-type]
        coverage,  # type: ignore[arg-type]
    )

    evidence = retrieval.search("faça um resumo dele", candidate_id=7, top_k=12)

    assert evidence
    assert coverage.call == (7, None, 12)


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

    def find_by_ids(self, candidate_ids) -> dict[int, Candidate]:  # noqa: ANN001
        return {7: self.candidate} if 7 in candidate_ids else {}


SECOND_CANDIDATE = Candidate(
    id=8,
    tse_id="TSE8",
    name="MARIA TRABALHO",
    ballot_name="MARIA",
    party="ABC",
    party_number=10,
    office="DEPUTADO FEDERAL",
    state="SP",
    candidate_number=1010,
)


class DiscoveryCandidates(StaticCandidates):
    def find_by_ids(self, candidate_ids) -> dict[int, Candidate]:  # noqa: ANN001
        available = {7: self.candidate, 8: SECOND_CANDIDATE}
        return {candidate_id: available[candidate_id] for candidate_id in candidate_ids}


def test_selected_candidate_without_chunks_returns_a_registry_summary() -> None:
    answer = RagService(EmptyRetrieval(), ForbiddenModel(), StaticCandidates()).ask(
        "faça um resumo dele",
        7,
    )

    assert "### ENRICO" in answer.answer
    assert "Nome completo" in answer.answer
    assert "limitado aos dados cadastrais do TSE" in answer.answer
    assert answer.candidate and answer.candidate["candidateNumber"] == 1515
    assert answer.sources == ()


class PropositionContexts:
    def context_by_camara_ids(self, candidate_id: int, camara_ids) -> dict[str, dict]:  # noqa: ANN001
        return {
            str(camara_id): {
                "propositionId": int(camara_id),
                "camaraId": int(camara_id),
                "title": f"Proposta de {candidate_id}",
            }
            for camara_id in camara_ids
        }


class EmptyDocumentContexts:
    def context_by_hashes(
        self,
        candidate_id: int,
        document_hashes: Sequence[str],
    ) -> dict[str, dict]:
        del candidate_id, document_hashes
        return {}


class EmptyHistoryContexts:
    def context_by_external_ids(
        self,
        candidate_id: int,
        external_ids: Sequence[str],
    ) -> dict[str, dict]:
        del candidate_id, external_ids
        return {}


class AuthorContexts:
    def context_by_proposition_ids(self, proposition_ids) -> dict[int, list[dict]]:  # noqa: ANN001
        return {
            int(proposition_id): [{"name": f"Autor {proposition_id}"}]
            for proposition_id in proposition_ids
        }


class TopicContexts:
    def context_by_proposition_ids(self, proposition_ids) -> dict[int, list[dict]]:  # noqa: ANN001
        return {int(proposition_id): [{"name": "Trabalho"}] for proposition_id in proposition_ids}


def discovery_context_loader() -> RagContextLoader:
    return RagContextLoader(
        DiscoveryCandidates(),
        PropositionContexts(),
        EmptyDocumentContexts(),
        EmptyHistoryContexts(),
        AuthorContexts(),
        TopicContexts(),
    )


class CapturingModel:
    def __init__(self) -> None:
        self.instructions = ""
        self.prompt = ""

    def generate(self, instructions: str, prompt: str) -> str:
        self.instructions = instructions
        self.prompt = prompt
        return "Resposta sobre Enrico [E1]."


class DiscoveryCapturingModel(CapturingModel):
    def generate(self, instructions: str, prompt: str) -> str:
        self.instructions = instructions
        self.prompt = prompt
        return "Enrico possui evidência [E1]. Maria possui evidência [E2]."


class EmptyModel:
    def generate(self, _instructions: str, _prompt: str) -> str:
        return ""


class FakeResponses:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeOpenAIClient:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = FakeResponses(responses)


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


def test_rag_discovers_candidates_and_keeps_each_proposition_attributed() -> None:
    model = DiscoveryCapturingModel()
    evidence = [result(101, candidate_id=7), result(202, candidate_id=8)]
    answer = RagService(
        StaticRetrieval(evidence),
        model,
        DiscoveryCandidates(),
        discovery_context_loader(),
    ).ask("Quais candidatos têm propostas para reduzir a escala 6x1?", None)

    assert "MODO DA CONSULTA: DISCOVERY" in model.prompt
    assert "Nome: ENRICO MISASI" in model.prompt
    assert "Nome: MARIA TRABALHO" in model.prompt
    assert '"title": "Proposta de 7"' in model.prompt
    assert '"title": "Proposta de 8"' in model.prompt
    assert answer.candidate is None
    assert {source["candidateId"] for source in answer.sources} == {7, 8}


def test_openai_model_retries_an_incomplete_empty_response() -> None:
    first = SimpleNamespace(
        output_text="",
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )
    second = SimpleNamespace(
        output_text="Síntese concluída [E1].",
        status="completed",
        incomplete_details=None,
    )
    client = FakeOpenAIClient([first, second])
    model = OpenAILanguageModel("test", "gpt-5-mini", 1_800)
    model.client = client  # type: ignore[assignment]

    answer = model.generate("instruções", "contexto")

    assert answer == "Síntese concluída [E1]."
    assert [call["max_output_tokens"] for call in client.responses.calls] == [1_800, 4_000]


def test_rag_returns_an_evidence_summary_when_model_text_is_empty() -> None:
    evidence = [result(101, candidate_id=7), result(202, candidate_id=8)]
    answer = RagService(
        StaticRetrieval(evidence),
        EmptyModel(),
        DiscoveryCandidates(),
        discovery_context_loader(),
    ).ask("Quais candidatos têm propostas para reduzir a escala 6x1?", None)

    assert "resultados diretamente sustentados" in answer.answer
    assert "### ENRICO" in answer.answer
    assert "### MARIA" in answer.answer
    assert "[E1]" in answer.answer and "[E2]" in answer.answer


def test_context_loader_attaches_authors_and_topics_to_proposition() -> None:
    context = discovery_context_loader().load(None, [result(101, candidate_id=7)])

    assert context.mode == "DISCOVERY"
    assert context.evidence[0].candidate.id == 7
    assert context.evidence[0].source_data["authors"] == [{"name": "Autor 101"}]
    assert context.evidence[0].source_data["topics"] == [{"name": "Trabalho"}]


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
