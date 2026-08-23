from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from app.domain import SearchResult
from app.retrieval import HybridSearch

from .prompt import POLICY, build_prompt

NO_EVIDENCE = (
    "Não foram encontradas evidências suficientes nas fontes indexadas "
    "para responder a esta pergunta."
)


class LanguageModel(Protocol):
    def generate(self, instructions: str, prompt: str) -> str: ...


class OpenAILanguageModel:
    def __init__(self, api_key: str | None, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, instructions: str, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model, instructions=instructions, input=prompt
        )
        return response.output_text.strip()


@dataclass(frozen=True, slots=True)
class RagAnswer:
    answer: str
    sources: tuple[dict, ...]

    def as_dict(self) -> dict:
        return {"answer": self.answer, "sources": list(self.sources)}


class RagService:
    def __init__(self, retrieval: HybridSearch, language_model: LanguageModel) -> None:
        self.retrieval = retrieval
        self.language_model = language_model

    def ask(self, question: str, candidate_id: int | None = None) -> RagAnswer:
        evidence = self.retrieval.search(question, candidate_id=candidate_id, top_k=8)
        if not evidence:
            return RagAnswer(NO_EVIDENCE, ())
        answer = self.language_model.generate(POLICY, build_prompt(question, evidence))
        return RagAnswer(answer, tuple(_source(item) for item in evidence))


def _source(item: SearchResult) -> dict:
    return {
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
