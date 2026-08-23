from __future__ import annotations

from typing import Protocol

from openai import OpenAI


class Embedder(Protocol):
    model: str

    def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str | None, model: str, dimension: int = 1536) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model, input=text, dimensions=self.dimension
        )
        vector = list(response.data[0].embedding)
        if len(vector) != self.dimension:
            raise ValueError(f"embedding dimension mismatch: {len(vector)}")
        return vector
