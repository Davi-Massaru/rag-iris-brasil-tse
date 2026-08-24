from __future__ import annotations

import json

from app.domain import utc_now

from .base import RepositorySupport


class IngestionRunRepository(RepositorySupport):
    def start(self, source: str, parameters: dict, source_hash: str | None = None) -> int:
        if source not in {"TSE_CANDIDATES", "TSE_PROPOSALS", "CAMARA", "RAG_INDEX"}:
            raise ValueError("invalid ingestion source")
        parameters_json = json.dumps(parameters, ensure_ascii=False, sort_keys=True)
        if self.objects is not None:
            target = self.objects.new("IngestionRun")
            self.objects.set_values(
                target,
                {
                    "Source": source,
                    "StartedAt": utc_now(),
                    "Status": "RUNNING",
                    "RecordsRead": 0,
                    "RecordsCreated": 0,
                    "RecordsUpdated": 0,
                    "RecordsSkipped": 0,
                    "RecordsFailed": 0,
                    "SourceHash": source_hash,
                    "ParametersJson": parameters_json,
                },
            )
            return self.objects.save(target)
        self.execute(
            f"""INSERT INTO {self.table("IngestionRun")}
            (Source,StartedAt,Status,RecordsRead,RecordsCreated,RecordsUpdated,RecordsSkipped,
             RecordsFailed,SourceHash,ParametersJson) VALUES (?,?,'RUNNING',0,0,0,0,0,?,?)""",
            (
                source,
                utc_now(),
                source_hash,
                parameters_json,
            ),
        )
        row = self.one(
            f"SELECT MAX(ID) FROM {self.table('IngestionRun')} WHERE Source=?", (source,)
        )
        return int(row[0])

    def increment(self, run_id: int, column: str, amount: int = 1) -> None:
        allowed = {
            "RecordsRead",
            "RecordsCreated",
            "RecordsUpdated",
            "RecordsSkipped",
            "RecordsFailed",
        }
        if column not in allowed or amount < 0:
            raise ValueError("invalid ingestion counter")
        self.execute(
            f"UPDATE {self.table('IngestionRun')} SET {column}=COALESCE({column},0)+? WHERE ID=?",
            (amount, run_id),
        )

    def finish(self, run_id: int, status: str, error: str | None = None) -> None:
        if status not in {"SUCCESS", "PARTIAL", "FAILED"}:
            raise ValueError("invalid ingestion status")
        changed = self.execute(
            f"""UPDATE {self.table("IngestionRun")} SET FinishedAt=?,Status=?,ErrorMessage=?
            WHERE ID=? AND Status='RUNNING'""",
            (utc_now(), status, error[:32000] if error else None, run_id),
        )
        if changed != 1:
            raise RuntimeError("ingestion run is not RUNNING")
