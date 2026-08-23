from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.domain import SearchResult


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchResult]],
    limit: int,
    k: int = 60,
) -> list[SearchResult]:
    scores: dict[int, float] = {}
    values: dict[int, SearchResult] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            values[item.chunk_id] = item
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    return [replace(values[chunk_id], score=scores[chunk_id]) for chunk_id in ordered]
