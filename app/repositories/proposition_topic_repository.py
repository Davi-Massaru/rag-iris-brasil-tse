from __future__ import annotations

from collections.abc import Sequence

from app.domain import TopicWrite, UpsertResult, utc_now

from .base import RepositorySupport


class PropositionTopicRepository(RepositorySupport):
    def upsert(self, value: TopicWrite) -> UpsertResult:
        row = self.one(
            f"SELECT ID,ExternalCode FROM {self.table('PropositionTopic')} WHERE Proposition=? AND Name=?",
            (value.proposition_id, value.name),
        )
        if row and row[1] == value.external_code:
            return UpsertResult(int(row[0]), "UNCHANGED")
        if row:
            self.execute(
                f"UPDATE {self.table('PropositionTopic')} SET ExternalCode=?,UpdatedAt=? WHERE ID=?",
                (value.external_code, utc_now(), int(row[0])),
            )
            return UpsertResult(int(row[0]), "UPDATED")
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("PropositionTopic")}
            (Proposition,ExternalCode,Name,CreatedAt,UpdatedAt) VALUES (?,?,?,?,?)""",
            (value.proposition_id, value.external_code, value.name, now, now),
        )
        inserted = self.one(
            f"SELECT ID FROM {self.table('PropositionTopic')} WHERE Proposition=? AND Name=?",
            (value.proposition_id, value.name),
        )
        return UpsertResult(int(inserted[0]), "INSERTED")

    def upsert_many(self, values: Sequence[TopicWrite]) -> list[UpsertResult]:
        if not values:
            return []
        proposition_id = values[0].proposition_id
        if any(value.proposition_id != proposition_id for value in values):
            raise ValueError("topics must share one proposition")
        unique_values = list({value.name: value for value in values}.values())
        rows = self.all(
            f"SELECT ID,ExternalCode,Name FROM {self.table('PropositionTopic')} WHERE Proposition=?",
            (proposition_id,),
        )
        by_name = {str(row[2]): row for row in rows}
        results: list[UpsertResult | None] = []
        inserted_names: list[str] = []
        for value in unique_values:
            row = by_name.get(value.name)
            if row and row[1] == value.external_code:
                results.append(UpsertResult(int(row[0]), "UNCHANGED"))
                continue
            if row:
                self.execute(
                    f"UPDATE {self.table('PropositionTopic')} SET ExternalCode=?,UpdatedAt=? WHERE ID=?",
                    (value.external_code, utc_now(), int(row[0])),
                )
                results.append(UpsertResult(int(row[0]), "UPDATED"))
                continue
            now = utc_now()
            self.execute(
                f"""INSERT INTO {self.table("PropositionTopic")}
                (Proposition,ExternalCode,Name,CreatedAt,UpdatedAt) VALUES (?,?,?,?,?)""",
                (proposition_id, value.external_code, value.name, now, now),
            )
            inserted_names.append(value.name)
            results.append(None)
        if inserted_names:
            rows = self.all(
                f"SELECT ID,Name FROM {self.table('PropositionTopic')} WHERE Proposition=?",
                (proposition_id,),
            )
            inserted_ids = {str(row[1]): int(row[0]) for row in rows}
        else:
            inserted_ids = {}
        names = iter(inserted_names)
        resolved: list[UpsertResult] = []
        for result in results:
            if result is not None:
                resolved.append(result)
                continue
            resolved.append(UpsertResult(inserted_ids[next(names)], "INSERTED"))
        return resolved

    def names(self, proposition_id: int) -> tuple[str, ...]:
        rows = self.all(
            f"SELECT Name FROM {self.table('PropositionTopic')} WHERE Proposition=? ORDER BY Name",
            (proposition_id,),
        )
        return tuple(str(row[0]) for row in rows)

    def context_by_proposition_ids(
        self,
        proposition_ids: Sequence[int],
    ) -> dict[int, list[dict]]:
        ids = tuple(dict.fromkeys(int(value) for value in proposition_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.all(
            f"""SELECT Proposition,ExternalCode,Name
            FROM {self.table("PropositionTopic")}
            WHERE Proposition IN ({placeholders}) ORDER BY Proposition,Name""",
            ids,
        )
        result: dict[int, list[dict]] = {}
        for row in rows:
            result.setdefault(int(row[0]), []).append(
                {
                    "externalCode": int(row[1]) if row[1] not in (None, "") else None,
                    "name": str(row[2]),
                }
            )
        return result
