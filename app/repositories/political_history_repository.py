from __future__ import annotations

from collections.abc import Sequence

from app.domain import HistoryWrite, UpsertResult, utc_now

from .base import RepositorySupport


class PoliticalHistoryRepository(RepositorySupport):
    def upsert(self, value: HistoryWrite) -> UpsertResult:
        row = self.one(
            f"""SELECT ID,Institution,Position,Party,State,StartDate,EndDate,Situation,SourceUrl
            FROM {self.table("PoliticalHistory")} WHERE Candidate=? AND ExternalId=?""",
            (value.candidate_id, value.external_id),
        )
        fields = (
            value.institution,
            value.position,
            value.party,
            value.state,
            value.start_date,
            value.end_date,
            value.situation,
            value.source_url,
        )
        if row and tuple(row[1:]) == fields:
            return UpsertResult(int(row[0]), "UNCHANGED")
        if row:
            self.execute(
                f"""UPDATE {self.table("PoliticalHistory")} SET
                Institution=?,Position=?,Party=?,State=?,StartDate=?,EndDate=?,Situation=?,
                SourceUrl=?,SourceCollectedAt=?,RawJson=?,UpdatedAt=? WHERE ID=?""",
                (*fields, value.collected_at, value.raw_json, utc_now(), int(row[0])),
            )
            return UpsertResult(int(row[0]), "UPDATED")
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("PoliticalHistory")}
            (Candidate,Institution,Position,Party,State,StartDate,EndDate,ExternalId,Situation,
             SourceUrl,SourceCollectedAt,RawJson,CreatedAt,UpdatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                value.candidate_id,
                value.institution,
                value.position,
                value.party,
                value.state,
                value.start_date,
                value.end_date,
                value.external_id,
                value.situation,
                value.source_url,
                value.collected_at,
                value.raw_json,
                now,
                now,
            ),
        )
        inserted = self.one(
            f"SELECT ID FROM {self.table('PoliticalHistory')} WHERE Candidate=? AND ExternalId=?",
            (value.candidate_id, value.external_id),
        )
        return UpsertResult(int(inserted[0]), "INSERTED")

    def list_for_chunks(self) -> list[tuple]:
        return self.all(
            f"""SELECT ID,Candidate,Institution,Position,Party,State,StartDate,EndDate,
            ExternalId,Situation,SourceUrl,SourceCollectedAt FROM {self.table("PoliticalHistory")}
            WHERE ExternalId IS NOT NULL ORDER BY ID"""
        )

    def context_by_external_ids(
        self,
        candidate_id: int,
        external_ids: Sequence[str],
    ) -> dict[str, dict]:
        ids = tuple(dict.fromkeys(str(value) for value in external_ids if value))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.all(
            f"""SELECT ID,Institution,Position,Party,State,StartDate,EndDate,ExternalId,
            Situation,SourceUrl,SourceCollectedAt FROM {self.table("PoliticalHistory")}
            WHERE Candidate=? AND ExternalId IN ({placeholders})""",
            (candidate_id, *ids),
        )
        return {
            str(row[7]): {
                "politicalHistoryId": int(row[0]),
                "institution": _optional(row[1]),
                "position": _optional(row[2]),
                "party": _optional(row[3]),
                "state": _optional(row[4]),
                "startDate": _optional(row[5]),
                "endDate": _optional(row[6]),
                "externalId": str(row[7]),
                "situation": _optional(row[8]),
                "sourceUrl": _optional(row[9]),
                "sourceCollectedAt": _optional(row[10]),
            }
            for row in rows
        }


def _optional(value) -> str | None:  # noqa: ANN001
    return None if value in (None, "") else str(value)
