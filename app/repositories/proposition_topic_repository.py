from __future__ import annotations

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

    def names(self, proposition_id: int) -> tuple[str, ...]:
        rows = self.all(
            f"SELECT Name FROM {self.table('PropositionTopic')} WHERE Proposition=? ORDER BY Name",
            (proposition_id,),
        )
        return tuple(str(row[0]) for row in rows)
