from __future__ import annotations

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
