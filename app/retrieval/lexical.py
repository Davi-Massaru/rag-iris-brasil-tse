from __future__ import annotations

import json
import re
import unicodedata

from app.domain import SearchResult
from app.repositories.base import RepositorySupport


class LexicalSearch(RepositorySupport):
    def search(
        self,
        query: str,
        candidate_id: int | None = None,
        source_type: str | None = None,
        top_k: int = 20,
    ) -> list[SearchResult]:
        rows = self._rows(candidate_id, source_type)
        phrase = _normalize(query)
        terms = tuple(dict.fromkeys(phrase.split()))
        ranked: list[SearchResult] = []
        for row in rows:
            haystack = _normalize(f"{row[4]} {row[5]}")
            phrase_hits = haystack.count(phrase) if phrase else 0
            term_hits = sum(haystack.count(term) for term in terms)
            if phrase_hits == 0 and term_hits == 0:
                continue
            ranked.append(_result(row, phrase_hits * 10.0 + term_hits))
        return sorted(ranked, key=lambda item: (-item.score, item.chunk_id))[:top_k]

    def _rows(self, candidate_id: int | None, source_type: str | None) -> list[tuple]:
        clauses: list[str] = []
        params: list[object] = []
        if candidate_id is not None:
            clauses.append("Candidate=?")
            params.append(candidate_id)
        if source_type:
            clauses.append("SourceType=?")
            params.append(source_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.all(
            f"""SELECT ID,Candidate,SourceType,SourceId,Title,Content,SourceUrl,MetadataJson
            FROM {self.table("PoliticalChunk")}{where}""",
            tuple(params),
        )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\W+", " ", plain.casefold()).strip()


def _result(row: tuple, score: float) -> SearchResult:
    try:
        metadata = json.loads(str(row[7] or "{}"))
    except json.JSONDecodeError:
        metadata = {}
    return SearchResult(
        chunk_id=int(row[0]),
        candidate_id=int(row[1]),
        source_type=str(row[2]),
        source_id=str(row[3]),
        title=str(row[4] or ""),
        content=str(row[5]),
        source_url=str(row[6] or ""),
        score=float(score),
        metadata=metadata,
    )
