from __future__ import annotations

import builtins
from typing import Any

from app.domain import Candidate, CandidateWrite, MatchResult, UpsertResult, utc_now

from .base import RepositorySupport

FIELDS = (
    "ID,TseId,Name,BallotName,Party,PartyNumber,Office,State,CandidateNumber,"
    "CamaraDeputyId,MatchStatus,MatchConfidence,SourceUrl"
)


class CandidateRepository(RepositorySupport):
    def find_by_id(self, candidate_id: int) -> Candidate | None:
        row = self.one(
            f"SELECT {FIELDS} FROM {self.table('Candidate')} WHERE ID=?",
            (candidate_id,),
        )
        return _candidate(row) if row else None

    def find_by_tse_id(self, tse_id: str) -> Candidate | None:
        row = self.one(
            f"SELECT {FIELDS} FROM {self.table('Candidate')} WHERE TseId=?",
            (tse_id,),
        )
        return _candidate(row) if row else None

    def upsert(self, value: CandidateWrite) -> UpsertResult:
        current = self.find_by_tse_id(value.tse_id)
        if current is None:
            return UpsertResult(self._insert(value), "INSERTED")
        if self._same(current, value):
            return UpsertResult(current.id, "UNCHANGED")
        self._update(current.id, value)
        return UpsertResult(current.id, "UPDATED")

    def save_match(self, candidate_id: int, match: MatchResult) -> None:
        deputy_id = match.deputy_id if match.status == "MATCHED" else None
        self.execute(
            f"""UPDATE {self.table("Candidate")}
            SET CamaraDeputyId=?,MatchStatus=?,MatchConfidence=?,UpdatedAt=? WHERE ID=?""",
            (deputy_id, str(match.status), match.confidence, utc_now(), candidate_id),
        )

    def list(
        self,
        name: str | None = None,
        party: str | None = None,
        state: str | None = None,
        office: str | None = None,
    ) -> builtins.list[Candidate]:
        clauses: list[str] = []
        params: list[Any] = []
        if name:
            clauses.append("(Name %STARTSWITH ? OR BallotName %STARTSWITH ?)")
            params.extend((name, name))
        for column, value in (("Party", party), ("State", state), ("Office", office)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value.upper())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.all(
            f"SELECT {FIELDS} FROM {self.table('Candidate')}{where} ORDER BY Name",
            tuple(params),
        )
        return [_candidate(row) for row in rows]

    def list_for_matching(self) -> builtins.list[Candidate]:
        rows = self.all(f"SELECT {FIELDS} FROM {self.table('Candidate')} ORDER BY ID")
        return [_candidate(row) for row in rows]

    def _insert(self, value: CandidateWrite) -> int:
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("Candidate")}
            (TseId,Name,BallotName,Party,PartyNumber,Office,State,CandidateNumber,
             SourceUrl,SourceCollectedAt,CreatedAt,UpdatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value.tse_id,
                value.name,
                value.ballot_name,
                value.party,
                value.party_number,
                value.office,
                value.state,
                value.candidate_number,
                value.source_url,
                value.collected_at,
                now,
                now,
            ),
        )
        inserted = self.find_by_tse_id(value.tse_id)
        if inserted is None:
            raise RuntimeError("candidate insert failed")
        return inserted.id

    def _update(self, candidate_id: int, value: CandidateWrite) -> None:
        self.execute(
            f"""UPDATE {self.table("Candidate")} SET
            Name=?,BallotName=?,Party=?,PartyNumber=?,Office=?,State=?,CandidateNumber=?,
            SourceUrl=?,SourceCollectedAt=?,UpdatedAt=? WHERE ID=?""",
            (
                value.name,
                value.ballot_name,
                value.party,
                value.party_number,
                value.office,
                value.state,
                value.candidate_number,
                value.source_url,
                value.collected_at,
                utc_now(),
                candidate_id,
            ),
        )

    @staticmethod
    def _same(current: Candidate, value: CandidateWrite) -> bool:
        return (
            current.name,
            current.ballot_name,
            current.party,
            current.party_number,
            current.office,
            current.state,
            current.candidate_number,
            current.source_url,
        ) == (
            value.name,
            value.ballot_name,
            value.party,
            value.party_number,
            value.office,
            value.state,
            value.candidate_number,
            value.source_url,
        )


def _candidate(row: Any) -> Candidate:
    return Candidate(
        id=int(row[0]),
        tse_id=str(row[1]),
        name=str(row[2]),
        ballot_name=str(row[3]) if row[3] is not None else None,
        party=str(row[4]) if row[4] is not None else None,
        party_number=int(row[5]) if row[5] is not None else None,
        office=str(row[6]),
        state=str(row[7]),
        candidate_number=int(row[8]) if row[8] is not None else None,
        camara_deputy_id=int(row[9]) if row[9] is not None else None,
        match_status=str(row[10]) if row[10] is not None else None,
        match_confidence=float(row[11]) if row[11] is not None else None,
        source_url=str(row[12]) if row[12] is not None else None,
    )
