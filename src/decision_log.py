"""Decision log: one SQLite row per automated decision, using the Governance Framework's minimum record (A8)."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["decision_id", "timestamp", "ticket_id", "stage", "input_summary", "model", "prediction", "alternatives",
          "sources_used", "threshold_applied", "action_taken", "reason", "guardrail_results", "prompt_version",
          "requirement_ids"]
JSON_FIELDS = {"model", "prediction", "alternatives", "sources_used", "guardrail_results", "requirement_ids"}


def db_path(url: str | None = None) -> Path:
    p = Path((url or os.getenv("DATABASE_URL", "sqlite:///./storage/decisions.db")).removeprefix("sqlite:///"))
    return p if p.is_absolute() else ROOT / p


class DecisionLog:
    def __init__(self, url: str | None = None):
        path = db_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS decisions ({', '.join(FIELDS)})")

    def write(self, **rec) -> str:
        rec = {"decision_id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), **rec}
        unknown = set(rec) - set(FIELDS)
        assert not unknown, f"unknown decision fields: {unknown}"
        row = [json.dumps(rec.get(f)) if f in JSON_FIELDS else rec.get(f) for f in FIELDS]
        self.conn.execute(f"INSERT INTO decisions VALUES ({', '.join('?' * len(FIELDS))})", row)
        self.conn.commit()  # commit per row so a crash mid-run never loses logged decisions
        return rec["decision_id"]

    def rows(self, **where) -> list[dict]:
        sql = "SELECT * FROM decisions" + (" WHERE " + " AND ".join(f"{k} = ?" for k in where) if where else "")
        cur = self.conn.execute(sql, list(where.values()))
        cols = [c[0] for c in cur.description]
        return [{c: json.loads(v) if c in JSON_FIELDS and v is not None else v for c, v in zip(cols, r)}
                for r in cur.fetchall()]
