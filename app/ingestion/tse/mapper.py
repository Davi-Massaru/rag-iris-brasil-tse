from __future__ import annotations

from datetime import datetime

from app.domain import CandidateWrite

from .contracts import TseCandidateRaw


def to_candidate(raw: TseCandidateRaw, source_url: str, collected_at: datetime) -> CandidateWrite:
    return CandidateWrite(
        tse_id=raw.candidate_sequence,
        name=raw.candidate_name.strip(),
        ballot_name=raw.ballot_name.strip() if raw.ballot_name else None,
        party=raw.party_abbreviation,
        party_number=raw.party_number,
        office=raw.office_name.upper(),
        state=raw.state.upper(),
        candidate_number=raw.candidate_number,
        source_url=source_url,
        collected_at=collected_at,
    )
