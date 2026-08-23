from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.ingestion.http import ExternalContractError

from .contracts import TseCandidateRaw

COLUMNS = {
    "ANO_ELEICAO",
    "SG_UF",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "NR_PARTIDO",
    "SG_PARTIDO",
}
TEXT_NULLS = {"", "#NULO", "#NE", "NÃO DIVULGÁVEL"}
NUMBER_NULLS = TEXT_NULLS | {"-1", "-3", "-4"}


@dataclass(frozen=True, slots=True)
class ParsedRow:
    line: int
    candidate: TseCandidateRaw | None
    error: str | None = None


def validate_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ExternalContractError("artifact is not a ZIP")
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            parts = PurePosixPath(member.filename.replace("\\", "/"))
            if parts.is_absolute() or ".." in parts.parts:
                raise ExternalContractError(f"unsafe ZIP member: {member.filename}")


def parse_candidates(path: Path) -> list[ParsedRow]:
    validate_zip(path)
    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if item.filename.lower().endswith(".csv")]
        brasil = [item for item in members if "BRASIL" in item.filename.upper()]
        selected = brasil or members
        if not selected:
            raise ExternalContractError("candidate CSV not found")
        return [result for member in selected for result in _parse_member(archive, member)]


def _parse_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> list[ParsedRow]:
    results: list[ParsedRow] = []
    with archive.open(member) as binary:
        reader = csv.DictReader(
            io.TextIOWrapper(binary, encoding="latin-1", newline=""),
            delimiter=";",
            quotechar='"',
        )
        missing = COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ExternalContractError(f"candidate CSV missing columns: {sorted(missing)}")
        for line, row in enumerate(reader, 2):
            try:
                candidate = _candidate(row)
            except ValueError as exc:
                results.append(ParsedRow(line, None, str(exc)))
                continue
            results.append(ParsedRow(line, candidate))
    return results


def _candidate(row: dict[str, str]) -> TseCandidateRaw:
    return TseCandidateRaw(
        election_year=_required_int(row, "ANO_ELEICAO"),
        state=_required_text(row, "SG_UF").upper(),
        office_code=_integer(row.get("CD_CARGO")),
        office_name=_required_text(row, "DS_CARGO").upper(),
        candidate_sequence=_required_text(row, "SQ_CANDIDATO"),
        candidate_number=_integer(row.get("NR_CANDIDATO")),
        candidate_name=_required_text(row, "NM_CANDIDATO"),
        ballot_name=_text(row.get("NM_URNA_CANDIDATO")),
        party_number=_integer(row.get("NR_PARTIDO")),
        party_abbreviation=_upper(row.get("SG_PARTIDO")),
    )


def _text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return None if cleaned.upper() in TEXT_NULLS else cleaned


def _upper(value: str | None) -> str | None:
    cleaned = _text(value)
    return cleaned.upper() if cleaned else None


def _integer(value: str | None) -> int | None:
    cleaned = (value or "").strip()
    if cleaned.upper() in NUMBER_NULLS:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"invalid integer: {cleaned!r}") from exc


def _required_text(row: dict[str, str], key: str) -> str:
    value = _text(row.get(key))
    if value is None:
        raise ValueError(f"required field {key} is empty")
    return value


def _required_int(row: dict[str, str], key: str) -> int:
    value = _integer(row.get(key))
    if value is None:
        raise ValueError(f"required field {key} is empty")
    return value
