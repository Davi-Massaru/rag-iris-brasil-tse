from __future__ import annotations

from collections.abc import Sequence

from app.domain import AuthorWrite, UpsertResult, utc_now

from .base import RepositorySupport


class PropositionAuthorRepository(RepositorySupport):
    def upsert(self, value: AuthorWrite) -> UpsertResult:
        rows = self.all(
            f"SELECT ID,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor FROM {self.table('PropositionAuthor')} WHERE Proposition=?",
            (value.proposition_id,),
        )
        row = next((item for item in rows if self._same_key(item, value)), None)
        fields = (
            value.camara_author_id,
            value.name,
            value.author_type,
            value.uri,
            1 if value.is_main_author else 0,
        )
        if row and tuple(row[1:]) == fields:
            return UpsertResult(int(row[0]), "UNCHANGED")
        if row:
            self.execute(
                f"""UPDATE {self.table("PropositionAuthor")} SET CamaraAuthorId=?,Name=?,
                AuthorType=?,Uri=?,IsMainAuthor=?,UpdatedAt=? WHERE ID=?""",
                (*fields, utc_now(), int(row[0])),
            )
            return UpsertResult(int(row[0]), "UPDATED")
        now = utc_now()
        self.execute(
            f"""INSERT INTO {self.table("PropositionAuthor")}
            (Proposition,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor,CreatedAt,UpdatedAt)
            VALUES (?,?,?,?,?,?,?,?)""",
            (value.proposition_id, *fields, now, now),
        )
        rows = self.all(
            f"SELECT ID,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor FROM {self.table('PropositionAuthor')} WHERE Proposition=?",
            (value.proposition_id,),
        )
        inserted = next(item for item in rows if self._same_key(item, value))
        return UpsertResult(int(inserted[0]), "INSERTED")

    def upsert_many(self, values: Sequence[AuthorWrite]) -> list[UpsertResult]:
        if not values:
            return []
        proposition_id = values[0].proposition_id
        if any(value.proposition_id != proposition_id for value in values):
            raise ValueError("authors must share one proposition")
        unique_values: list[AuthorWrite] = []
        seen: set[tuple] = set()
        for value in values:
            key = self._value_key(value)
            if key not in seen:
                seen.add(key)
                unique_values.append(value)
        rows = self.all(
            f"SELECT ID,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor FROM {self.table('PropositionAuthor')} WHERE Proposition=?",
            (proposition_id,),
        )
        results: list[UpsertResult | None] = []
        inserted_values: list[AuthorWrite] = []
        for value in unique_values:
            row = next((item for item in rows if self._same_key(item, value)), None)
            fields = self._fields(value)
            if row and tuple(row[1:]) == fields:
                results.append(UpsertResult(int(row[0]), "UNCHANGED"))
                continue
            if row:
                self.execute(
                    f"""UPDATE {self.table("PropositionAuthor")} SET CamaraAuthorId=?,Name=?,
                    AuthorType=?,Uri=?,IsMainAuthor=?,UpdatedAt=? WHERE ID=?""",
                    (*fields, utc_now(), int(row[0])),
                )
                results.append(UpsertResult(int(row[0]), "UPDATED"))
                continue
            now = utc_now()
            self.execute(
                f"""INSERT INTO {self.table("PropositionAuthor")}
                (Proposition,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor,CreatedAt,UpdatedAt)
                VALUES (?,?,?,?,?,?,?,?)""",
                (proposition_id, *fields, now, now),
            )
            inserted_values.append(value)
            results.append(None)
        if inserted_values:
            rows = self.all(
                f"SELECT ID,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor FROM {self.table('PropositionAuthor')} WHERE Proposition=?",
                (proposition_id,),
            )
        inserted = iter(inserted_values)
        resolved: list[UpsertResult] = []
        for result in results:
            if result is not None:
                resolved.append(result)
                continue
            value = next(inserted)
            row = next(item for item in rows if self._same_key(item, value))
            resolved.append(UpsertResult(int(row[0]), "INSERTED"))
        return resolved

    def names(self, proposition_id: int) -> tuple[str, ...]:
        rows = self.all(
            f"SELECT Name FROM {self.table('PropositionAuthor')} WHERE Proposition=? ORDER BY ID",
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
            f"""SELECT Proposition,CamaraAuthorId,Name,AuthorType,Uri,IsMainAuthor
            FROM {self.table("PropositionAuthor")}
            WHERE Proposition IN ({placeholders}) ORDER BY Proposition,ID""",
            ids,
        )
        result: dict[int, list[dict]] = {}
        for row in rows:
            result.setdefault(int(row[0]), []).append(
                {
                    "camaraAuthorId": int(row[1]) if row[1] not in (None, "") else None,
                    "name": str(row[2]),
                    "authorType": str(row[3]) if row[3] not in (None, "") else None,
                    "uri": str(row[4]) if row[4] not in (None, "") else None,
                    "isMainAuthor": row[5] not in (None, "", 0, "0", False),
                }
            )
        return result

    @staticmethod
    def _same_key(row: tuple, value: AuthorWrite) -> bool:
        if value.uri:
            return row[4] == value.uri
        return (
            str(row[2]).strip().casefold() == value.name.strip().casefold()
            and row[3] == value.author_type
        )

    @staticmethod
    def _fields(value: AuthorWrite) -> tuple:
        return (
            value.camara_author_id,
            value.name,
            value.author_type,
            value.uri,
            1 if value.is_main_author else 0,
        )

    @staticmethod
    def _value_key(value: AuthorWrite) -> tuple:
        if value.uri:
            return ("uri", value.uri)
        return ("name", value.name.strip().casefold(), value.author_type)
