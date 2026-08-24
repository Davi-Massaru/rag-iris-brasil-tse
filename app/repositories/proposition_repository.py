from __future__ import annotations

from app.domain import PropositionWrite, UpsertResult, utc_now

from .base import RepositorySupport


class PropositionRepository(RepositorySupport):
    def upsert(self, value: PropositionWrite) -> UpsertResult:
        row = self.one(
            f"""SELECT ID,Candidate,Type,Number,Year,Title,Summary,DetailedSummary,
            PresentationDate,Status,SourceUrl FROM {self.table("Proposition")} WHERE CamaraId=?""",
            (value.camara_id,),
        )
        fields = (
            value.type,
            value.number,
            value.year,
            value.title,
            value.summary,
            value.detailed_summary,
            value.presentation_date,
            value.status,
            value.source_url,
        )
        if row and tuple(row[2:]) == fields:
            return UpsertResult(int(row[0]), "UNCHANGED")
        if row:
            self.execute(
                f"""UPDATE {self.table("Proposition")} SET Type=?,Number=?,Year=?,Title=?,
                Summary=?,DetailedSummary=?,PresentationDate=?,Status=?,SourceUrl=?,
                SourceCollectedAt=?,UpdatedAt=? WHERE ID=?""",
                (*fields, value.collected_at, utc_now(), int(row[0])),
            )
            action = "UPDATED_CONFLICT" if int(row[1]) != value.candidate_id else "UPDATED"
            return UpsertResult(int(row[0]), action)
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("Proposition")}
            (Candidate,CamaraId,Type,Number,Year,Title,Summary,DetailedSummary,PresentationDate,
             Status,SourceUrl,SourceCollectedAt,CreatedAt,UpdatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (value.candidate_id, value.camara_id, *fields, value.collected_at, now, now),
        )
        inserted = self.one(
            f"SELECT ID FROM {self.table('Proposition')} WHERE CamaraId=?", (value.camara_id,)
        )
        return UpsertResult(int(inserted[0]), "INSERTED")

    def list_by_candidate(self, candidate_id: int) -> list[dict]:
        rows = self.all(
            f"""SELECT ID,CamaraId,Type,Number,Year,Title,Summary,DetailedSummary,
            PresentationDate,Status,SourceUrl FROM {self.table("Proposition")}
            WHERE Candidate=? ORDER BY Year DESC,Number DESC""",
            (candidate_id,),
        )
        keys = (
            "id",
            "camaraId",
            "type",
            "number",
            "year",
            "title",
            "summary",
            "detailedSummary",
            "presentationDate",
            "status",
            "sourceUrl",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def list_for_chunks(self) -> list[tuple]:
        return self.all(
            f"""SELECT ID,Candidate,CamaraId,Title,Summary,DetailedSummary,Status,SourceUrl,
            SourceCollectedAt FROM {self.table("Proposition")} ORDER BY ID"""
        )

    def repair_invalid_years(self) -> int:
        rows = self.all(
            f"""SELECT ID,Type,Number,YEAR(PresentationDate)
            FROM {self.table("Proposition")}
            WHERE (Year IS NULL OR Year<=0) AND PresentationDate IS NOT NULL"""
        )
        repaired = 0
        for proposition_id, proposition_type, number, year in rows:
            parts = [str(proposition_type or "").strip(), str(number) if number is not None else ""]
            stem = " ".join(part for part in parts if part)
            title = f"{stem}/{int(year)}" if stem else str(int(year))
            self.execute(
                f"""UPDATE {self.table("Proposition")}
                SET Year=?,Title=?,UpdatedAt=? WHERE ID=?""",
                (int(year), title, utc_now(), int(proposition_id)),
            )
            repaired += 1
        return repaired
