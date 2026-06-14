"""Cold memory tier — durable, append-only-with-supersede store (SQLite, WAL).

`remember()` writes a new row; updating a `key` supersedes the old row instead of
deleting it, so history survives (the ERROR/RESULT trail is the point). `recall()`
returns only live (non-superseded) rows by default, newest first, filterable by kind,
tag, and a substring query. `context_pack()` assembles the hot tier: a small, bounded
bundle of the most relevant live memories to drop into a prompt.

Vector recall (sqlite-vec) is a V2 add-on; V1 uses keyword/tag recall to avoid native
build dependencies.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from midas.core.agents.summary import ProofLevel
from midas.core.receipts.models import utcnow_iso

from .models import MemoryEntry, MemoryKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    proof_level TEXT    NOT NULL,
    sources     TEXT    NOT NULL,
    tags        TEXT    NOT NULL,
    superseded  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mem_kind ON memory(kind);
CREATE INDEX IF NOT EXISTS idx_mem_key ON memory(kind, key);
CREATE INDEX IF NOT EXISTS idx_mem_live ON memory(superseded);
"""

_SEP = "\x1f"  # unit separator — safe joiner for sources/tags lists


class MemoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ── write ────────────────────────────────────────────────────────────────
    def remember(
        self,
        kind: MemoryKind,
        key: str,
        content: str,
        *,
        proof_level: ProofLevel = ProofLevel.LOW,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        """Store a fact. Supersedes any live entry with the same (kind, key)."""
        entry = MemoryEntry(
            kind=kind,
            key=key,
            content=content,
            proof_level=proof_level,
            sources=sources or [],
            tags=tags or [],
            ts=utcnow_iso(),
        )
        with self._lock:
            self._conn.execute(
                "UPDATE memory SET superseded=1 WHERE kind=? AND key=? AND superseded=0",
                (kind.value, key),
            )
            cur = self._conn.execute(
                "INSERT INTO memory(ts,kind,key,content,proof_level,sources,tags,superseded) "
                "VALUES(?,?,?,?,?,?,?,0)",
                (
                    entry.ts,
                    kind.value,
                    key,
                    content,
                    entry.proof_level.value,
                    _SEP.join(entry.sources),
                    _SEP.join(entry.tags),
                ),
            )
            self._conn.commit()
            entry.id = cur.lastrowid
        return entry

    # ── convenience writers for the typed namespaces ──────────────────────────
    def record_decision(
        self, key: str, *, chose: str, rejected: list[str], why: str,
        sources: list[str] | None = None, proof_level: ProofLevel = ProofLevel.LOW,
    ) -> MemoryEntry:
        rejected_str = "; ".join(rejected) or "(none)"
        content = f"Chose: {chose}. Rejected: {rejected_str}. Why: {why}"
        return self.remember(
            MemoryKind.DECISION, key, content, proof_level=proof_level, sources=sources or []
        )

    def record_result(
        self, key: str, *, outcome: str, metrics: dict[str, float] | None = None,
        sources: list[str] | None = None,
    ) -> MemoryEntry:
        m = ", ".join(f"{k}={v}" for k, v in (metrics or {}).items())
        content = outcome if not m else f"{outcome} ({m})"
        # Results are observed facts — proof rises only if the metric is sourced.
        proof = ProofLevel.MEDIUM if sources else ProofLevel.LOW
        return self.remember(
            MemoryKind.RESULT, key, content, proof_level=proof,
            sources=sources or [], tags=["track"],
        )

    def record_error(
        self, key: str, *, what_failed: str, why: str, sources: list[str] | None = None,
    ) -> MemoryEntry:
        content = f"Did not work: {what_failed}. Because: {why}"
        return self.remember(
            MemoryKind.ERROR, key, content, sources=sources or [], tags=["lesson"]
        )

    # ── read ───────────────────────────────────────────────────────────────────
    def recall(
        self,
        *,
        kind: MemoryKind | None = None,
        query: str | None = None,
        tag: str | None = None,
        include_superseded: bool = False,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        sql = "SELECT id,ts,kind,key,content,proof_level,sources,tags,superseded FROM memory"
        clauses: list[str] = []
        params: list[object] = []
        if not include_superseded:
            clauses.append("superseded=0")
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind.value)
        if query:
            clauses.append("(content LIKE ? OR key LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row(r) for r in rows]

    def history(self, kind: MemoryKind, key: str) -> list[MemoryEntry]:
        """Every version of a fact, oldest→newest (the 'last time we tried' trail)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,ts,kind,key,content,proof_level,sources,tags,superseded "
                "FROM memory WHERE kind=? AND key=? ORDER BY id ASC",
                (kind.value, key),
            ).fetchall()
        return [self._row(r) for r in rows]

    def context_pack(self, *, per_kind: int = 3, query: str | None = None) -> str:
        """Assemble the hot tier: a small bundle of the most relevant live memories."""
        lines: list[str] = []
        for k in MemoryKind:
            entries = self.recall(kind=k, query=query, limit=per_kind)
            if not entries:
                continue
            lines.append(f"## {k.value.upper()}")
            for e in entries:
                badge = f"[{e.proof_level.value}]"
                src = f" (src: {', '.join(e.sources)})" if e.sources else ""
                lines.append(f"- {badge} {e.content}{src}")
        return "\n".join(lines)

    @staticmethod
    def _row(r: tuple) -> MemoryEntry:
        return MemoryEntry(
            id=r[0],
            ts=r[1],
            kind=MemoryKind(r[2]),
            key=r[3],
            content=r[4],
            proof_level=ProofLevel(r[5]),
            sources=[s for s in r[6].split(_SEP) if s],
            tags=[t for t in r[7].split(_SEP) if t],
            superseded=bool(r[8]),
        )
