"""Market Radar: competitor tracking with dated, sourced snapshots.

V1 keeps this intentionally local and deterministic. A competitor has watched URLs;
`watch_all()` fetches them, hashes the content, records changes as MARKET memory,
and writes receipts. No ads API or private scraping is implied.
"""

from __future__ import annotations

import builtins
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from midas.core.agents.summary import ProofLevel
from midas.core.memory import MemoryKind
from midas.core.receipts.models import Decision, Taint, sha256_hex, utcnow_iso
from midas.core.web import Fetcher

_SCHEMA = """
CREATE TABLE IF NOT EXISTS competitors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts TEXT NOT NULL,
    name       TEXT NOT NULL,
    url        TEXT NOT NULL,
    notes      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comp_url ON competitors(url);
CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    competitor_id INTEGER NOT NULL,
    url           TEXT NOT NULL,
    status        INTEGER NOT NULL,
    content_hash  TEXT NOT NULL,
    excerpt       TEXT NOT NULL,
    changed       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_comp ON competitor_snapshots(competitor_id);
"""


@dataclass(frozen=True)
class Competitor:
    id: int
    created_ts: str
    name: str
    url: str
    notes: str = ""


@dataclass(frozen=True)
class CompetitorSnapshot:
    competitor_id: int
    name: str
    url: str
    status: int
    content_hash: str
    changed: bool
    change_kind: str
    excerpt: str
    ts: str


class CompetitorStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, name: str, url: str, *, notes: str = "") -> Competitor:
        ts = utcnow_iso()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO competitors(created_ts,name,url,notes) VALUES(?,?,?,?)",
                (ts, name.strip(), url.strip(), notes.strip()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT id,created_ts,name,url,notes FROM competitors WHERE url=?", (url.strip(),)
            ).fetchone()
        return self._row_competitor(row)

    def list(self) -> builtins.list[Competitor]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,created_ts,name,url,notes FROM competitors ORDER BY id ASC"
            ).fetchall()
        return [self._row_competitor(r) for r in rows]

    def watch_all(
        self,
        *,
        fetcher: Fetcher,
        memory: Any = None,
        ledger: Any = None,
        run_id: str = "market-watch",
    ) -> builtins.list[CompetitorSnapshot]:
        return [
            self.snapshot(c, fetcher=fetcher, memory=memory, ledger=ledger, run_id=run_id)
            for c in self.list()
        ]

    def snapshot(
        self,
        competitor: Competitor,
        *,
        fetcher: Fetcher,
        memory: Any = None,
        ledger: Any = None,
        run_id: str = "market-watch",
    ) -> CompetitorSnapshot:
        page = fetcher.fetch(competitor.url)
        text = page.text if page.ok else ""
        content_hash = sha256_hex(text.encode("utf-8")) if text else ""
        previous = self._latest_hash(competitor.id)
        changed = page.ok and previous is not None and previous != content_hash
        initial = page.ok and previous is None
        change_kind = "unreachable"
        if initial:
            change_kind = "initial"
        elif changed:
            change_kind = "changed"
        elif page.ok:
            change_kind = "unchanged"

        snap = CompetitorSnapshot(
            competitor_id=competitor.id,
            name=competitor.name,
            url=competitor.url,
            status=page.status,
            content_hash=content_hash,
            changed=changed,
            change_kind=change_kind,
            excerpt=_excerpt(text),
            ts=utcnow_iso(),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO competitor_snapshots"
                "(ts,competitor_id,url,status,content_hash,excerpt,changed) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    snap.ts, snap.competitor_id, snap.url, snap.status, snap.content_hash,
                    snap.excerpt, 1 if snap.changed else 0,
                ),
            )
            self._conn.commit()

        if memory is not None:
            proof = ProofLevel.MEDIUM if page.ok else ProofLevel.LOW
            memory.remember(
                MemoryKind.MARKET,
                f"competitor:{competitor.id}:{competitor.url}",
                _market_memory_content(snap),
                proof_level=proof,
                sources=[competitor.url] if page.ok else [],
                tags=["competitor", change_kind],
            )
        if ledger is not None:
            ledger.append(
                run_id=run_id,
                agent="market-radar",
                tool="competitor.snapshot",
                decision=Decision.ALLOW,
                inputs={"competitor_id": competitor.id, "url": competitor.url},
                outputs={"status": snap.status, "change_kind": change_kind},
                taint_out=Taint.UNTRUSTED,
            )
        return snap

    def _latest_hash(self, competitor_id: int) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT content_hash FROM competitor_snapshots "
                "WHERE competitor_id=? AND content_hash!='' ORDER BY id DESC LIMIT 1",
                (competitor_id,),
            ).fetchone()
        return row[0] if row else None

    def get(self, competitor_id: int) -> Competitor | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id,created_ts,name,url,notes FROM competitors WHERE id=?",
                (competitor_id,),
            ).fetchone()
        return self._row_competitor(row) if row else None

    def delete(self, competitor_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM competitors WHERE id=?", (competitor_id,))
            self._conn.execute(
                "DELETE FROM competitor_snapshots WHERE competitor_id=?", (competitor_id,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def snapshots(
        self, competitor_id: int, *, limit: int = 50
    ) -> builtins.list[CompetitorSnapshot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts,competitor_id,url,status,content_hash,excerpt,changed,id "
                "FROM competitor_snapshots WHERE competitor_id=? ORDER BY id ASC LIMIT ?",
                (competitor_id, limit),
            ).fetchall()
        comp = self.get(competitor_id)
        name = comp.name if comp else ""
        # Walk oldest→newest so we can detect "initial" as the first OK reading.
        seen_ok = False
        forward: builtins.list[CompetitorSnapshot] = []
        for r in rows:
            changed = bool(r[6])
            status = int(r[3])
            content_hash = r[4] or ""
            if not (200 <= status < 300) or not content_hash:
                change_kind = "unreachable"
            elif not seen_ok:
                change_kind = "initial"
                seen_ok = True
            elif changed:
                change_kind = "changed"
            else:
                change_kind = "unchanged"
            forward.append(
                CompetitorSnapshot(
                    competitor_id=int(r[1]),
                    name=name,
                    url=r[2],
                    status=status,
                    content_hash=content_hash,
                    changed=changed,
                    change_kind=change_kind,
                    excerpt=r[5] or "",
                    ts=r[0],
                )
            )
        # Return newest-first so the UI can render most-recent at top.
        return list(reversed(forward))

    @staticmethod
    def _row_competitor(row: tuple) -> Competitor:
        return Competitor(id=row[0], created_ts=row[1], name=row[2], url=row[3], notes=row[4])


def _excerpt(text: str, *, limit: int = 360) -> str:
    clean = " ".join(text.split())
    return clean[:limit]


def _market_memory_content(snap: CompetitorSnapshot) -> str:
    if snap.change_kind == "changed":
        impact = "Possible pricing, offer, SEO, or positioning change. Review before acting."
    elif snap.change_kind == "initial":
        impact = "Initial competitor baseline captured."
    elif snap.change_kind == "unchanged":
        impact = "No visible page-content change since last snapshot."
    else:
        impact = "Source unreachable; do not infer a market change."
    return (
        f"{snap.name} {snap.change_kind} at {snap.url}. "
        f"Status={snap.status}. Hash={snap.content_hash or 'none'}. {impact}"
    )
