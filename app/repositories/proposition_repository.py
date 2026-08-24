from __future__ import annotations

from collections.abc import Sequence

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

    def context_by_camara_ids(
        self,
        candidate_id: int,
        camara_ids: Sequence[str],
    ) -> dict[str, dict]:
        ids = tuple(dict.fromkeys(int(value) for value in camara_ids if str(value).isdigit()))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.all(
            f"""SELECT ID,CamaraId,Type,Number,Year,Title,Summary,DetailedSummary,
            PresentationDate,Status,SourceUrl FROM {self.table("Proposition")}
            WHERE Candidate=? AND CamaraId IN ({placeholders})""",
            (candidate_id, *ids),
        )
        return {
            str(row[1]): {
                "propositionId": int(row[0]),
                "camaraId": int(row[1]),
                "type": _optional(row[2]),
                "number": _optional_int(row[3]),
                "year": _optional_int(row[4]),
                "title": _optional(row[5]),
                "summary": _optional(row[6]),
                "detailedSummary": _optional(row[7]),
                "presentationDate": _optional(row[8]),
                "status": _optional(row[9]),
                "sourceUrl": _optional(row[10]),
            }
            for row in rows
        }

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


def _optional(value) -> str | None:  # noqa: ANN001
    return None if value in (None, "") else str(value)


def _optional_int(value) -> int | None:  # noqa: ANN001
    return None if value in (None, "") else int(value)
