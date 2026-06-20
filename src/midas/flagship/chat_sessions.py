"""WS-Sessions — durable chat history for the Hermes/OpenClaw-style sidebar.

Goal: when the operator reloads the dashboard they see their past conversations
in a sidebar and can click one to resume. The Claude-Code experience, but
local-first.

Storage shape:
- ``.midas/sessions/index.db`` (SQLite) — one row per session with title,
  timestamps, message count, and total cost. Indexed by ``last_msg_ts DESC`` so
  the sidebar query is a single ordered scan.
- ``.midas/sessions/<run_id>.jsonl`` — one JSON object per message. Append-only.
  We never rewrite history; renaming a session only touches the index DB row.

This module owns nothing that the agent loop needs at runtime — chat.py keeps
its current `run_chat` shape, then calls into ``ChatSessionStore.append`` after
the bundle is produced.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionSummary:
    id: str
    title: str
    created_ts: float
    last_msg_ts: float
    message_count: int
    cost_total: float

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_ts": self.created_ts,
            "last_msg_ts": self.last_msg_ts,
            "message_count": self.message_count,
            "cost_total": round(self.cost_total, 6),
        }


@dataclass(frozen=True)
class SessionMessage:
    ts: float
    role: str  # "user" or "assistant"
    content: str
    model: str
    cost_usd: float

    def to_json(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "cost_usd": round(self.cost_usd, 6),
        }


_VALID_ID = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:-_.")


def _safe_id(run_id: str) -> str:
    """Reject path traversal — session ids are filesystem path components."""
    if not run_id:
        raise ValueError("empty session id")
    if any(c not in _VALID_ID for c in run_id):
        raise ValueError(f"invalid session id chars: {run_id!r}")
    if len(run_id) > 80:
        raise ValueError("session id too long")
    return run_id


class ChatSessionStore:
    """Thread-unsafe (we run inside a single FastAPI event loop) JSONL + sqlite store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "index.db"
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    last_msg_ts REAL NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    cost_total REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS sessions_last_msg ON sessions(last_msg_ts DESC)"
            )
            conn.commit()

    def list_recent(self, *, limit: int = 50) -> list[SessionSummary]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, title, created_ts, last_msg_ts, message_count, cost_total "
                "FROM sessions ORDER BY last_msg_ts DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [SessionSummary(*row) for row in rows]

    def get_summary(self, run_id: str) -> SessionSummary | None:
        rid = _safe_id(run_id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT id, title, created_ts, last_msg_ts, message_count, cost_total "
                "FROM sessions WHERE id = ?",
                (rid,),
            ).fetchone()
        return SessionSummary(*row) if row else None

    def messages(self, run_id: str) -> list[SessionMessage]:
        rid = _safe_id(run_id)
        path = self.root / f"{rid}.jsonl"
        if not path.exists():
            return []
        out: list[SessionMessage] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    out.append(
                        SessionMessage(
                            ts=float(payload.get("ts", 0.0)),
                            role=str(payload.get("role", "user")),
                            content=str(payload.get("content", "")),
                            model=str(payload.get("model", "")),
                            cost_usd=float(payload.get("cost_usd", 0.0)),
                        )
                    )
                except (TypeError, ValueError):
                    continue
        return out

    def append(
        self,
        run_id: str,
        *,
        role: str,
        content: str,
        model: str = "",
        cost_usd: float = 0.0,
        title_seed: str | None = None,
    ) -> SessionSummary:
        """Append one message; create the session row if it doesn't exist yet."""
        rid = _safe_id(run_id)
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        now = time.time()
        msg = SessionMessage(ts=now, role=role, content=content, model=model, cost_usd=cost_usd)
        path = self.root / f"{rid}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg.to_json(), ensure_ascii=False) + "\n")
        with closing(sqlite3.connect(self.db_path)) as conn:
            existing = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (rid,)).fetchone()
            if existing is None:
                title = _make_title(title_seed or content)
                conn.execute(
                    "INSERT INTO sessions "
                    "(id, title, created_ts, last_msg_ts, message_count, cost_total) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (rid, title, now, now, cost_usd),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET last_msg_ts = ?, message_count = message_count + 1, "
                    "cost_total = cost_total + ? WHERE id = ?",
                    (now, cost_usd, rid),
                )
            conn.commit()
        summary = self.get_summary(rid)
        if summary is None:
            raise RuntimeError("session row missing after insert")  # never expected
        return summary

    def rename(self, run_id: str, title: str) -> SessionSummary | None:
        rid = _safe_id(run_id)
        clean = title.strip()[:120]
        if not clean:
            raise ValueError("title required")
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (clean, rid))
            conn.commit()
        return self.get_summary(rid)

    def delete(self, run_id: str) -> bool:
        rid = _safe_id(run_id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            removed = conn.execute("DELETE FROM sessions WHERE id = ?", (rid,)).rowcount
            conn.commit()
        path = self.root / f"{rid}.jsonl"
        if path.exists():
            path.unlink()
        return removed > 0


def _make_title(seed: str) -> str:
    """First 60 chars of the first user message, stripped of newlines."""
    flat = " ".join(seed.split())[:60]
    return flat or "Untitled chat"


__all__ = ["ChatSessionStore", "SessionMessage", "SessionSummary"]
