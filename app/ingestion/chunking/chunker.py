from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Protocol

import tiktoken


class Encoding(Protocol):
    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...


class TokenChunker:
    def __init__(
        self,
        model: str,
        size: int = 700,
        overlap: int = 100,
        encoding: Encoding | None = None,
    ) -> None:
        if size <= 0 or overlap < 0 or overlap >= size:
            raise ValueError("invalid chunk size/overlap")
        if encoding is not None:
            self.encoding = encoding
            self.size = size
            self.overlap = overlap
            return
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        self.size = size
        self.overlap = overlap

    def split(self, text: str) -> tuple[str, ...]:
        tokens = self.encoding.encode(normalize_content(text))
        if not tokens:
            return ()
        step = self.size - self.overlap
        chunks = [
            self.encoding.decode(tokens[start : start + self.size]).strip()
            for start in range(0, len(tokens), step)
        ]
        return tuple(chunk[:32000] for chunk in chunks if chunk)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text))


def normalize_content(value: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", value)).strip()


def content_hash(value: str) -> str:
    return hashlib.sha256(normalize_content(value).encode("utf-8")).hexdigest()
