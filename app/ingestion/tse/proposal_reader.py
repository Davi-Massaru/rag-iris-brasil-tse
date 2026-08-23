from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pypdf import PdfReader

from app.ingestion.http import ExternalContractError

from .parser import validate_zip

PROPOSAL_PATTERN = re.compile(
    r"^(?P<year>\d{4})(?P<state>BR|[A-Z]{2})(?P<tse_id>\d+)_(?P<sequence>\d{2})\.pdf$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProposalPdf:
    year: int
    state: str
    tse_id: str
    sequence: str
    file_name: str
    document_hash: str
    pages: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(
            f"[Página {index}]\n{content}" for index, content in enumerate(self.pages, 1) if content
        )


def read_proposals(path: Path) -> list[ProposalPdf]:
    validate_zip(path)
    proposals: list[ProposalPdf] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            name = PurePosixPath(member.filename).name
            match = PROPOSAL_PATTERN.fullmatch(name)
            if member.is_dir() or not match:
                continue
            content = archive.read(member)
            proposals.append(_proposal(member.filename, match, content))
    return proposals


def _proposal(file_name: str, match: re.Match[str], content: bytes) -> ProposalPdf:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = tuple((page.extract_text() or "").strip() for page in reader.pages)
    except Exception as exc:
        raise ExternalContractError(f"invalid proposal PDF {file_name}") from exc
    return ProposalPdf(
        year=int(match.group("year")),
        state=match.group("state").upper(),
        tse_id=match.group("tse_id"),
        sequence=match.group("sequence"),
        file_name=file_name,
        document_hash=hashlib.sha256(content).hexdigest(),
        pages=pages,
    )
