from __future__ import annotations

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

    def names(self, proposition_id: int) -> tuple[str, ...]:
        rows = self.all(
            f"SELECT Name FROM {self.table('PropositionAuthor')} WHERE Proposition=? ORDER BY ID",
            (proposition_id,),
        )
        return tuple(str(row[0]) for row in rows)

    @staticmethod
    def _same_key(row: tuple, value: AuthorWrite) -> bool:
        if value.uri:
            return row[4] == value.uri
        return (
            str(row[2]).strip().casefold() == value.name.strip().casefold()
            and row[3] == value.author_type
        )
