from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime

from app.domain import AuthorWrite, HistoryWrite, PropositionWrite, TopicWrite

from .contracts import (
    ExternalMandate,
    HistoryItem,
    PropositionAuthor,
    PropositionDetail,
    PropositionTopic,
)


def history_write(
    candidate_id: int, deputy_id: int, item: HistoryItem, source_url: str, collected_at: datetime
) -> HistoryWrite:
    raw = _canonical(item.model_dump(exclude_none=True))
    suffix = (
        f"{item.idLegislatura}:{item.dataHora}"
        if item.dataHora
        else hashlib.sha256(raw.encode()).hexdigest()
    )
    return HistoryWrite(
        candidate_id=candidate_id,
        institution="CAMARA",
        position="DEPUTADO FEDERAL",
        party=item.siglaPartido,
        state=item.siglaUf,
        start_date=_iso_date(item.dataHora),
        end_date=None,
        external_id=f"CAMARA_HIST:{deputy_id}:{suffix}",
        situation=item.situacao or item.descricaoStatus,
        source_url=source_url,
        collected_at=collected_at,
        raw_json=raw,
    )


def mandate_write(
    candidate_id: int,
    deputy_id: int,
    item: ExternalMandate,
    source_url: str,
    collected_at: datetime,
) -> HistoryWrite:
    raw_data = {**item.model_dump(exclude_none=True), "datePrecision": "YEAR"}
    identity = "|".join(
        str(value or "")
        for value in (
            item.cargo,
            item.siglaUf,
            item.municipio,
            item.anoInicio,
            item.anoFim,
            item.siglaPartidoEleicao,
        )
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:48]
    return HistoryWrite(
        candidate_id=candidate_id,
        institution="CAMARA",
        position=item.cargo,
        party=item.siglaPartidoEleicao,
        state=item.siglaUf,
        start_date=_year_date(item.anoInicio, 1, 1),
        end_date=_year_date(item.anoFim, 12, 31),
        external_id=f"CAMARA_EXT:{deputy_id}:{digest}",
        situation=f"Município: {item.municipio}" if item.municipio else None,
        source_url=source_url,
        collected_at=collected_at,
        raw_json=_canonical(raw_data),
    )


def proposition_write(
    candidate_id: int, item: PropositionDetail, collected_at: datetime
) -> PropositionWrite:
    presentation_date = _iso_date(item.dataApresentacao)
    year = item.ano if item.ano and item.ano > 0 else None
    if year is None and presentation_date is not None:
        year = presentation_date.year
    parts = [item.siglaTipo, str(item.numero) if item.numero is not None else None]
    title = " ".join(part for part in parts if part)
    if year is not None:
        title = f"{title}/{year}" if title else str(year)
    status = item.statusProposicao
    return PropositionWrite(
        candidate_id=candidate_id,
        camara_id=item.id,
        type=item.siglaTipo,
        number=item.numero,
        year=year,
        title=title,
        summary=item.ementa,
        detailed_summary=item.ementaDetalhada,
        presentation_date=presentation_date,
        status=(status.descricaoSituacao or status.descricaoTramitacao) if status else None,
        source_url=item.uri,
        collected_at=collected_at,
    )


def author_write(proposition_id: int, item: PropositionAuthor) -> AuthorWrite:
    match = re.search(r"/(\d+)$", item.uri or "")
    return AuthorWrite(
        proposition_id=proposition_id,
        camara_author_id=int(match.group(1)) if match else None,
        name=item.nome.strip(),
        author_type=item.tipo,
        uri=item.uri,
        is_main_author=item.proponente in (1, True),
    )


def topic_write(proposition_id: int, item: PropositionTopic) -> TopicWrite:
    return TopicWrite(proposition_id, item.codTema, item.tema.strip())


def _canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def _year_date(value: str | None, month: int, day: int) -> date | None:
    return date(int(value), month, day) if value and value.isdigit() else None
