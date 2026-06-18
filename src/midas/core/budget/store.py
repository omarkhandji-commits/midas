"""Crash-safe spend store (SQLite, WAL). Source of truth for the budget fuse."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    run_id  TEXT,
    task_id TEXT,
    skill   TEXT,
    persona TEXT,
    kind    TEXT,
    model   TEXT,
    usd     REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spend_ts ON spend(ts);
CREATE INDEX IF NOT EXISTS idx_spend_task ON spend(task_id);
"""


class SpendStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_columns()
        self._conn.commit()

    def record(
        self,
        usd: float,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        skill: str | None = None,
        persona: str | None = None,
        kind: str | None = None,
        model: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO spend(ts, run_id, task_id, skill, persona, kind, model, usd) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    run_id,
                    task_id,
                    skill,
                    persona,
                    kind,
                    model,
                    usd,
                ),
            )
            self._conn.commit()

    def total(
        self,
        *,
        since_iso: str | None = None,
        task_id: str | None = None,
        skill: str | None = None,
        persona: str | None = None,
    ) -> float:
        query = "SELECT COALESCE(SUM(usd), 0) FROM spend WHERE 1=1"
        params: list[object] = []
        if since_iso is not None:
            query += " AND ts >= ?"
            params.append(since_iso)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if skill is not None:
            query += " AND skill = ?"
            params.append(skill)
        if persona is not None:
            query += " AND persona = ?"
            params.append(persona)
        with self._lock:
            cur = self._conn.execute(query, params)
            return float(cur.fetchone()[0])

    def _migrate_columns(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(spend)")}
        for name in ("skill", "persona"):
            if name not in existing:
                self._conn.execute(f"ALTER TABLE spend ADD COLUMN {name} TEXT")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_spend_skill ON spend(skill)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_spend_persona ON spend(persona)")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
