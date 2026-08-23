from __future__ import annotations

import json
import re
from datetime import datetime

from app.domain import ChunkWrite, utc_now
from app.repositories import PropositionAuthorRepository, PropositionTopicRepository

from .chunker import TokenChunker, content_hash


class PoliticalChunkBuilder:
    def __init__(
        self,
        chunker: TokenChunker,
        authors: PropositionAuthorRepository,
        topics: PropositionTopicRepository,
    ) -> None:
        self.chunker = chunker
        self.authors = authors
        self.topics = topics

    def proposition(self, row: tuple) -> tuple[ChunkWrite, ...]:
        proposition_id, candidate_id, camara_id, title, summary, detail, status, url, collected = (
            row
        )
        text = "\n".join(
            line
            for line in (
                f"Título: {title}",
                f"Autores: {'; '.join(self.authors.names(int(proposition_id)))}",
                f"Temas: {'; '.join(self.topics.names(int(proposition_id)))}",
                f"Ementa: {summary or ''}",
                f"Ementa detalhada: {detail or ''}",
                f"Situação: {status or ''}",
            )
            if not line.endswith(": ")
        )
        return self._build(
            int(candidate_id),
            "PROPOSITION",
            str(camara_id),
            str(title or ""),
            text,
            str(url or ""),
            collected,
            {"camaraId": camara_id},
        )

    def document(self, row: tuple) -> tuple[ChunkWrite, ...]:
        (
            _,
            candidate_id,
            year,
            title,
            url,
            resource_id,
            file_name,
            document_hash,
            raw_text,
            collected,
        ) = row
        return self._build(
            int(candidate_id),
            "GOVERNMENT_PROPOSAL",
            str(document_hash),
            str(title or ""),
            str(raw_text or ""),
            str(url),
            collected,
            {"electionYear": year, "resourceId": resource_id, "fileName": file_name},
        )

    def history(self, row: tuple) -> tuple[ChunkWrite, ...]:
        (
            _,
            candidate_id,
            institution,
            position,
            party,
            state,
            start,
            end,
            external_id,
            situation,
            url,
            collected,
        ) = row
        period = "–".join(item for item in (_year(start), _year(end)) if item)
        text = "\n".join(
            line
            for line in (
                f"Instituição: {institution}",
                f"Cargo/Função: {position or ''}",
                f"Partido: {party or ''}",
                f"UF: {state or ''}",
                f"Período: {period}",
                f"Situação: {situation or ''}",
            )
            if not line.endswith(": ")
        )
        return self._build(
            int(candidate_id),
            "POLITICAL_HISTORY",
            str(external_id),
            str(position or "Histórico político"),
            text,
            str(url or ""),
            collected,
            {},
        )

    def _build(
        self,
        candidate_id: int,
        source_type: str,
        source_id: str,
        title: str,
        text: str,
        source_url: str,
        collected_at: datetime | None,
        metadata: dict,
    ) -> tuple[ChunkWrite, ...]:
        chunks = self.chunker.split(text)
        return tuple(
            ChunkWrite(
                candidate_id=candidate_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=index,
                title=title,
                content=chunk,
                source_url=source_url,
                metadata_json=json.dumps(
                    {**metadata, **_pages(chunk)}, ensure_ascii=False, sort_keys=True
                ),
                content_hash=content_hash(chunk),
                token_count=self.chunker.count(chunk),
                collected_at=collected_at or utc_now(),
            )
            for index, chunk in enumerate(chunks)
        )


def _year(value) -> str:  # noqa: ANN001
    return str(value)[:4] if value else ""


def _pages(text: str) -> dict[str, int]:
    pages = [int(value) for value in re.findall(r"\[Página (\d+)\]", text)]
    return {"pageStart": min(pages), "pageEnd": max(pages)} if pages else {}
