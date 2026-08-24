from __future__ import annotations

import builtins
from collections.abc import Sequence
from typing import Any

from app.domain import Candidate, CandidateWrite, MatchResult, UpsertResult, utc_now

from .base import RepositorySupport

FIELDS = (
    "ID,TseId,Name,BallotName,Party,PartyNumber,Office,State,CandidateNumber,"
    "CamaraDeputyId,MatchStatus,MatchConfidence,SourceUrl"
)


class CandidateRepository(RepositorySupport):
    def find_by_id(self, candidate_id: int) -> Candidate | None:
        if self.objects is not None:
            value = self.objects.open_id("Candidate", candidate_id)
            return _candidate_object(value) if value is not None else None
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

    def find_by_ids(self, candidate_ids: Sequence[int]) -> dict[int, Candidate]:
        ids = tuple(dict.fromkeys(int(value) for value in candidate_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.all(
            f"SELECT {FIELDS} FROM {self.table('Candidate')} WHERE ID IN ({placeholders})",
            ids,
        )
        values = [_candidate(row) for row in rows]
        return {candidate.id: candidate for candidate in values}

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
        if self.objects is not None:
            value = self.objects.open_id("Candidate", candidate_id, for_update=True)
            if value is None:
                return
            self.objects.set_values(
                value,
                {
                    "CamaraDeputyId": deputy_id,
                    "MatchStatus": str(match.status),
                    "MatchConfidence": match.confidence,
                    "UpdatedAt": utc_now(),
                },
            )
            self.objects.save(value)
            return
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
        if self.objects is not None:
            target = self.objects.new("Candidate")
            self.objects.set_values(
                target,
                {
                    "TseId": value.tse_id,
                    "Name": value.name,
                    "BallotName": value.ballot_name,
                    "Party": value.party,
                    "PartyNumber": value.party_number,
                    "Office": value.office,
                    "State": value.state,
                    "CandidateNumber": value.candidate_number,
                    "SourceUrl": value.source_url,
                    "SourceCollectedAt": value.collected_at,
                    "CreatedAt": now,
                    "UpdatedAt": now,
                },
            )
            return self.objects.save(target)
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
        if self.objects is not None:
            target = self.objects.open_id("Candidate", candidate_id, for_update=True)
            if target is None:
                raise RuntimeError("candidate disappeared during update")
            self.objects.set_values(
                target,
                {
                    "Name": value.name,
                    "BallotName": value.ballot_name,
                    "Party": value.party,
                    "PartyNumber": value.party_number,
                    "Office": value.office,
                    "State": value.state,
                    "CandidateNumber": value.candidate_number,
                    "SourceUrl": value.source_url,
                    "SourceCollectedAt": value.collected_at,
                    "UpdatedAt": utc_now(),
                },
            )
            self.objects.save(target)
            return
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
        ballot_name=_optional_str(row[3]),
        party=_optional_str(row[4]),
        party_number=_optional_int(row[5]),
        office=str(row[6]),
        state=str(row[7]),
        candidate_number=_optional_int(row[8]),
        camara_deputy_id=_optional_int(row[9]),
        match_status=_optional_str(row[10]),
        match_confidence=_optional_float(row[11]),
        source_url=_optional_str(row[12]),
    )


def _candidate_object(value: Any) -> Candidate:
    return _candidate(
        (
            value._Id(),
            value.TseId,
            value.Name,
            value.BallotName,
            value.Party,
            value.PartyNumber,
            value.Office,
            value.State,
            value.CandidateNumber,
            value.CamaraDeputyId,
            value.MatchStatus,
            value.MatchConfidence,
            value.SourceUrl,
        )
    )


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_int(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None


def _optional_float(value: Any) -> float | None:
    return float(value) if value not in (None, "") else None
