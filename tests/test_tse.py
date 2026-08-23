from __future__ import annotations

import zipfile
from pathlib import Path
from typing import cast

import pytest

from app.ingestion.http import ExternalContractError, HttpClient
from app.ingestion.tse.client import TseClient
from app.ingestion.tse.contracts import TseDataset, TseResource
from app.ingestion.tse.parser import parse_candidates, validate_zip

pytestmark = pytest.mark.unit
HEADER = (
    "ANO_ELEICAO;SG_UF;CD_CARGO;DS_CARGO;SQ_CANDIDATO;NR_CANDIDATO;"
    "NM_CANDIDATO;NM_URNA_CANDIDATO;NR_PARTIDO;SG_PARTIDO\n"
)


def write_zip(path: Path, member: str, content: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, content.encode("latin-1"))


def test_parse_latin1_candidate_and_null_sentinel(tmp_path: Path) -> None:
    path = tmp_path / "candidates.zip"
    row = "2026;SP;6;DEPUTADO FEDERAL;123456;1010;JOÃO SILVA;#NULO;10;ABC\n"
    write_zip(path, "consulta_cand_2026_BRASIL.csv", HEADER + row)

    parsed = parse_candidates(path)

    assert len(parsed) == 1
    assert parsed[0].candidate is not None
    assert parsed[0].candidate.candidate_name == "JOÃO SILVA"
    assert parsed[0].candidate.ballot_name is None
    assert parsed[0].candidate.candidate_sequence == "123456"


def test_parser_records_invalid_row_without_discarding_file(tmp_path: Path) -> None:
    path = tmp_path / "candidates.zip"
    row = "2026;SP;X;DEPUTADO FEDERAL;123456;1010;NOME;URNA;10;ABC\n"
    write_zip(path, "BRASIL.csv", HEADER + row)

    parsed = parse_candidates(path)

    assert parsed[0].candidate is None
    assert "invalid integer" in (parsed[0].error or "")


def test_zip_traversal_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.zip"
    write_zip(path, "../candidate.csv", HEADER)

    with pytest.raises(ExternalContractError, match="unsafe ZIP member"):
        validate_zip(path)


def test_tse_selects_only_active_official_candidate_resource(settings) -> None:  # noqa: ANN001
    active = TseResource(
        id="1",
        name="candidatos",
        format="CSV",
        state="active",
        url="https://cdn.tse.jus.br/candidates.zip",
    )
    dataset = TseDataset(id="x", name="x", title="x", resources=(active,))

    selected = TseClient(settings, cast(HttpClient, object())).candidate_resource(dataset)

    assert selected.id == "1"
