from __future__ import annotations

from typing import Protocol

from openai import OpenAI


class Embedder(Protocol):
    model: str

    def embed(self, text: str, /) -> list[float]: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str | None, model: str, dimension: int = 1536) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_many((text,))[0]

    def embed_many(self, texts: tuple[str, ...] | list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.model, input=list(texts), dimensions=self.dimension
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise ValueError(
                f"embedding batch size mismatch: expected {len(texts)}, got {len(vectors)}"
            )
        for vector in vectors:
            if len(vector) != self.dimension:
                raise ValueError(f"embedding dimension mismatch: {len(vector)}")
        return vectors
