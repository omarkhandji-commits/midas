"""Research cache — reuse search hits, fetched pages, and summaries across runs.

Token-economy is a top priority. Without a cache, every scan re-pays for the same
fetches and summaries. Keys are stable SHA-256 digests over the request shape so two
identical queries hit the same row regardless of when/where they ran.

Cold tier only (SQLite WAL). TTL is per-entry: a result expires when older than its
declared lifetime so stale evidence can't quietly back a Proof-First claim. `get()`
returns None on miss or expiry — the caller refetches and writes back fresh.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    kind      TEXT NOT NULL,
    value     TEXT NOT NULL,
    created   TEXT NOT NULL,
    expires   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_kind ON cache(kind);
"""


def cache_key(*parts: Any) -> str:
    """Stable digest over the request shape. Order-sensitive; case-sensitive."""
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ResearchCache:
    def __init__(
        self,
        path: str | Path,
        *,
        default_ttl: timedelta = timedelta(days=7),
        clock: Any = None,
    ) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._default_ttl = default_ttl
        self._now = clock or (lambda: datetime.now(UTC))

    def get(self, key: str) -> str | None:
        now = self._now().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires FROM cache WHERE key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        if row[1] <= now:
            self.evict(key)  # stale: refuse to serve evidence past its TTL
            return None
        return row[0]

    def put(
        self,
        key: str,
        value: str,
        *,
        kind: str = "generic",
        ttl: timedelta | None = None,
    ) -> None:
        now = self._now()
        expires = (now + (ttl or self._default_ttl)).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(key,kind,value,created,expires) VALUES(?,?,?,?,?)",
                (key, kind, value, now.isoformat(), expires),
            )
            self._conn.commit()

    def evict(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.commit()

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, COUNT(*) FROM cache GROUP BY kind"
            ).fetchall()
        return {r[0]: r[1] for r in rows}
