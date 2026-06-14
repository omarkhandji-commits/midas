"""Crash-safe spend store (SQLite, WAL). Source of truth for the budget fuse."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    run_id  TEXT,
    task_id TEXT,
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
        self._conn.commit()

    def record(
        self,
        usd: float,
        *,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        kind: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO spend(ts, run_id, task_id, kind, model, usd) VALUES (?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), run_id, task_id, kind, model, usd),
            )
            self._conn.commit()

    def total(self, *, since_iso: Optional[str] = None, task_id: Optional[str] = None) -> float:
        query = "SELECT COALESCE(SUM(usd), 0) FROM spend WHERE 1=1"
        params: list[object] = []
        if since_iso is not None:
            query += " AND ts >= ?"
            params.append(since_iso)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        with self._lock:
            cur = self._conn.execute(query, params)
            return float(cur.fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
