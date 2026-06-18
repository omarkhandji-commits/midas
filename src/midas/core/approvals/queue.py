"""Persistent approval queue — the human side of QUEUE_APPROVAL.

When the Sentinel returns QUEUE_APPROVAL, the tool call is parked here (SQLite WAL)
instead of disappearing. The operator approves or rejects from any channel (CLI,
Telegram, dashboard) and the queue is the single source of truth across them.

Properties:
- a request is PENDING until exactly one resolve call moves it to APPROVED or REJECTED;
- resolves are idempotent (re-resolving a closed request raises, so two channels can't
  silently double-fire);
- a TTL is supported — `expire_pending(now)` rejects-on-timeout in line with
  `policy.approval.reject_on_timeout: true`;
- only an authorized owner_id may resolve (defense against a hijacked channel speaking
  for the user); the resolver is stored on the receipt so audit names a real human.

Receipts: every approve/reject writes a receipt (verifiable trail of who said yes).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from midas.core.receipts.models import Decision, utcnow_iso


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalError(Exception):
    pass


@dataclass
class ApprovalRequest:
    id: int
    run_id: str
    agent: str
    tool: str
    action: str
    summary: str
    payload: dict[str, Any]
    status: ApprovalStatus
    created_ts: str
    risk: str = "medium"
    estimated_cost_usd: float = 0.0
    expires_ts: str | None = None
    resolved_ts: str | None = None
    resolver: str | None = None
    note: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_ts   TEXT    NOT NULL,
    run_id       TEXT    NOT NULL,
    agent        TEXT    NOT NULL,
    tool         TEXT    NOT NULL,
    action       TEXT    NOT NULL,
    summary      TEXT    NOT NULL,
    payload      TEXT    NOT NULL,
    risk         TEXT    NOT NULL DEFAULT 'medium',
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    expires_ts   TEXT,
    status       TEXT    NOT NULL,
    resolved_ts  TEXT,
    resolver     TEXT,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_apv_status ON approvals(status);
"""


class ApprovalQueue:
    def __init__(
        self,
        path: str | Path,
        *,
        ledger: Any = None,
        owner_ids: set[str] | None = None,
    ) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate_columns()
        self._conn.commit()
        self._ledger = ledger
        # If empty, ANY caller is accepted (single-user dev mode). In production the
        # operator's chat id / username goes here.
        self._owner_ids = set(owner_ids or [])

    # ── write ────────────────────────────────────────────────────────────────
    def enqueue(
        self,
        *,
        run_id: str,
        agent: str,
        tool: str,
        action: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        risk: str | None = None,
        estimated_cost_usd: float = 0.0,
        expires_in: timedelta | None = None,
    ) -> ApprovalRequest:
        created = datetime.now(UTC)
        ts = created.isoformat()
        expires_ts = (created + (expires_in or timedelta(hours=24))).isoformat()
        risk_level = risk or _infer_risk(action=action, tool=tool)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO approvals("
                "created_ts,run_id,agent,tool,action,summary,payload,risk,"
                "estimated_cost_usd,expires_ts,status"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ts,
                    run_id,
                    agent,
                    tool,
                    action,
                    summary,
                    json.dumps(payload or {}),
                    risk_level,
                    float(estimated_cost_usd),
                    expires_ts,
                    ApprovalStatus.PENDING.value,
                ),
            )
            self._conn.commit()
            req_id = cur.lastrowid
            if req_id is None:
                raise ApprovalError("approval insert did not return an id")
        return ApprovalRequest(
            id=req_id, run_id=run_id, agent=agent, tool=tool, action=action,
            summary=summary, payload=payload or {}, status=ApprovalStatus.PENDING,
            created_ts=ts, risk=risk_level, estimated_cost_usd=float(estimated_cost_usd),
            expires_ts=expires_ts,
        )

    def approve(self, request_id: int, *, by: str, note: str | None = None) -> ApprovalRequest:
        return self._resolve(request_id, ApprovalStatus.APPROVED, by=by, note=note)

    def reject(self, request_id: int, *, by: str, note: str | None = None) -> ApprovalRequest:
        return self._resolve(request_id, ApprovalStatus.REJECTED, by=by, note=note)

    def expire_pending(self, *, older_than: timedelta, now: datetime | None = None) -> int:
        """Reject-on-timeout (policy.approval.reject_on_timeout)."""
        n = now or datetime.now(UTC)
        cutoff = (n - older_than).isoformat()
        ts = utcnow_iso()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE approvals SET status=?, resolved_ts=?, resolver=?, note=? "
                "WHERE status=? AND created_ts<?",
                (ApprovalStatus.EXPIRED.value, ts, "system",
                 "auto-expired (reject_on_timeout)", ApprovalStatus.PENDING.value, cutoff),
            )
            self._conn.commit()
            return cur.rowcount

    # ── read ──────────────────────────────────────────────────────────────────
    def pending(self) -> list[ApprovalRequest]:
        return self._select("WHERE status=? ORDER BY id ASC", (ApprovalStatus.PENDING.value,))

    def get(self, request_id: int) -> ApprovalRequest | None:
        rows = self._select("WHERE id=?", (request_id,))
        return rows[0] if rows else None

    # ── internals ─────────────────────────────────────────────────────────────
    def _resolve(
        self,
        request_id: int,
        new_status: ApprovalStatus,
        *,
        by: str,
        note: str | None,
    ) -> ApprovalRequest:
        if self._owner_ids and by not in self._owner_ids:
            raise ApprovalError(f"resolver {by!r} not authorized")
        ts = utcnow_iso()
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM approvals WHERE id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise ApprovalError(f"approval {request_id} not found")
            if row[0] != ApprovalStatus.PENDING.value:
                raise ApprovalError(
                    f"approval {request_id} already {row[0]} (idempotency guard)"
                )
            self._conn.execute(
                "UPDATE approvals SET status=?, resolved_ts=?, resolver=?, note=? WHERE id=?",
                (new_status.value, ts, by, note, request_id),
            )
            self._conn.commit()

        req = self.get(request_id)
        if req is None:
            raise ApprovalError(f"approval {request_id} disappeared after resolve")
        if self._ledger is not None:
            decision = Decision.ALLOW if new_status == ApprovalStatus.APPROVED else Decision.DENY
            self._ledger.append(
                run_id=req.run_id, agent="approvals", tool=req.tool, decision=decision,
                inputs={"approval_id": req.id, "action": req.action},
                outputs={"status": new_status.value, "by": by, "note": note},
                approval_id=str(req.id),
            )
        return req

    def _select(self, where: str, params: tuple) -> list[ApprovalRequest]:
        # `where` is always an internal constant clause (see callers: pending()/get());
        # user-supplied values are bound via `params`, never formatted into the SQL.
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,created_ts,run_id,agent,tool,action,summary,payload,status,"
                "resolved_ts,resolver,note,risk,estimated_cost_usd,expires_ts "
                "FROM approvals " + where,  # nosec B608
                params,
            ).fetchall()
        return [
            ApprovalRequest(
                id=r[0], created_ts=r[1], run_id=r[2], agent=r[3], tool=r[4], action=r[5],
                summary=r[6], payload=json.loads(r[7] or "{}"),
                status=ApprovalStatus(r[8]), resolved_ts=r[9], resolver=r[10], note=r[11],
                risk=r[12] or "medium", estimated_cost_usd=float(r[13] or 0.0),
                expires_ts=r[14],
            )
            for r in rows
        ]

    def _migrate_columns(self) -> None:
        existing = {row[1] for row in self._conn.execute("PRAGMA table_info(approvals)")}
        columns = {
            "risk": "TEXT NOT NULL DEFAULT 'medium'",
            "estimated_cost_usd": "REAL NOT NULL DEFAULT 0.0",
            "expires_ts": "TEXT",
        }
        for name, ddl in columns.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE approvals ADD COLUMN {name} {ddl}")


def _infer_risk(*, action: str, tool: str) -> str:
    joined = f"{action} {tool}".lower()
    if any(word in joined for word in ("payment", "stripe", "price", "pay")):
        return "money"
    if any(word in joined for word in ("execute", "code", "mcp", "tool")):
        return "code"
    if any(word in joined for word in ("send", "email", "publish", "social", "egress")):
        return "send"
    if any(word in joined for word in ("write", "repo", "file", "install")):
        return "write"
    return "medium"
