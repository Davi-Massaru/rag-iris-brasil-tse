from __future__ import annotations

import json

from app.domain import SearchResult
from app.repositories.base import RepositorySupport


class CoverageSearch(RepositorySupport):
    """Return deterministic evidence distributed across a long source document."""

    def search(
        self,
        candidate_id: int,
        source_type: str | None,
        top_k: int,
    ) -> list[SearchResult]:
        where = "Candidate=?"
        params: tuple[object, ...] = (candidate_id,)
        if source_type is not None:
            where += " AND SourceType=?"
            params = (candidate_id, source_type)
        rows = self.all(
            f"""SELECT ID,Candidate,SourceType,SourceId,Title,Content,SourceUrl,
            MetadataJson,ChunkIndex FROM {self.table("PoliticalChunk")}
            WHERE {where} ORDER BY SourceType,SourceId,ChunkIndex,ID""",
            params,
        )
        sampled = _representative_sample(rows, top_k)
        results: list[SearchResult] = []
        for position, row in enumerate(sampled, 1):
            metadata = _metadata(row[7])
            metadata["coveragePosition"] = position
            metadata["coverageTotal"] = len(sampled)
            results.append(_result(row, 1.0 / position, metadata))
        return results


class TopicFrequencySearch(RepositorySupport):
    """Use relational facts for frequency questions instead of semantic guessing."""

    def search(self, candidate_id: int, top_k: int) -> list[SearchResult]:
        rows = self.all(
            f"""SELECT TOP {int(top_k)} topic.Name,COUNT(*) AS Frequency,MIN(prop.SourceUrl)
            FROM {self.table("PropositionTopic")} topic
            JOIN {self.table("Proposition")} prop ON prop.ID=topic.Proposition
            WHERE prop.Candidate=? GROUP BY topic.Name
            ORDER BY Frequency DESC,topic.Name ASC""",
            (candidate_id,),
        )
        return [
            SearchResult(
                chunk_id=-position,
                candidate_id=candidate_id,
                source_type="PROPOSITION_TOPIC_AGGREGATE",
                source_id=f"TOPIC:{row[0]}",
                title=f"Tema recorrente: {row[0]}",
                content=(
                    f"Tema oficial da Câmara: {row[0]}\n"
                    f"Quantidade de proposições associadas ao candidato: {int(row[1])}.\n"
                    "Método: contagem SQL dos temas oficiais persistidos no IRIS."
                ),
                source_url=str(row[2] or "https://dadosabertos.camara.leg.br/"),
                score=float(row[1]),
                metadata={"frequency": int(row[1]), "method": "SQL_COUNT"},
            )
            for position, row in enumerate(rows, 1)
        ]


def _representative_sample(rows: list[tuple], limit: int) -> list[tuple]:
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[0]]
    positions = [round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)]
    return [rows[index] for index in dict.fromkeys(positions)]


def _metadata(value: object) -> dict:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _result(row: tuple, score: float, metadata: dict) -> SearchResult:
    return SearchResult(
        chunk_id=int(row[0]),
        candidate_id=int(row[1]),
        source_type=str(row[2]),
        source_id=str(row[3]),
        title=str(row[4] or ""),
        content=str(row[5]),
        source_url=str(row[6] or ""),
        score=score,
        metadata=metadata,
    )
