from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Link(Contract):
    rel: str
    href: str


class CollectionEnvelope(Contract):
    dados: tuple[dict[str, Any], ...]
    links: tuple[Link, ...]


class EntityEnvelope(Contract):
    dados: dict[str, Any]
    links: tuple[Link, ...]


class DeputySummary(Contract):
    id: int
    uri: str
    nome: str
    siglaPartido: str | None = None
    siglaUf: str | None = None
    idLegislatura: int | None = None


class DeputyStatus(Contract):
    nome: str | None = None
    nomeEleitoral: str | None = None
    siglaPartido: str | None = None
    siglaUf: str | None = None
    idLegislatura: int | None = None


class DeputyDetail(Contract):
    id: int
    nomeCivil: str
    ultimoStatus: DeputyStatus


class HistoryItem(Contract):
    id: int | None = None
    uri: str | None = None
    nome: str | None = None
    nomeEleitoral: str | None = None
    siglaPartido: str | None = None
    siglaUf: str | None = None
    idLegislatura: int | None = None
    dataHora: str | None = None
    situacao: str | None = None
    condicaoEleitoral: str | None = None
    descricaoStatus: str | None = None


class ExternalMandate(Contract):
    cargo: str | None = None
    siglaUf: str | None = None
    municipio: str | None = None
    anoInicio: str | None = None
    anoFim: str | None = None
    siglaPartidoEleicao: str | None = None
    uriPartidoEleicao: str | None = None


class PropositionSummary(Contract):
    id: int
    uri: str
    siglaTipo: str | None = None
    numero: int | None = None
    ano: int | None = None
    ementa: str | None = None
    dataApresentacao: str | None = None


class PropositionStatus(Contract):
    descricaoSituacao: str | None = None
    descricaoTramitacao: str | None = None


class PropositionDetail(PropositionSummary):
    ementaDetalhada: str | None = None
    statusProposicao: PropositionStatus | None = None


class PropositionAuthor(Contract):
    uri: str | None = None
    nome: str
    tipo: str | None = None
    proponente: int | bool | None = None


class PropositionTopic(Contract):
    codTema: int | None = None
    tema: str
