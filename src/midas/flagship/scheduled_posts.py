"""Scheduled-post queue — pending social posts with a target time.

Why
---
`social.publish` is APPROVE-tier and fires immediately on resolve. To plan
content ahead ("publish this Tuesday 9am"), we need a queue the operator
can browse on a calendar and the runtime can drain at the right time.

Design
------
- Pure data store, JSON-backed. No network, no scheduler thread — the
  caller drains. A separate worker (cron or `midas drain`) is responsible
  for actually firing when ``scheduled_at_iso`` <= now.
- Each post carries its own canonical intent fields (platform, handle,
  text, media). When it fires, the runtime re-plans through
  ``plan_social_publish`` so the same sha256-intent check applies.
- Status transitions are explicit and one-way: ``pending`` → one of
  ``published`` / ``failed`` / ``cancelled``. We never silently delete.

Honest constraints
------------------
- We do NOT auto-fire. The store records intent; firing requires the
  operator's approval queue path like any other ``social.publish``.
- We do NOT validate the post content here — `plan_social_publish`
  remains the single source of truth at execute time.
"""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

ScheduledStatus = Literal["pending", "queued", "published", "failed", "cancelled"]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime:
    # Accept Z suffix or explicit offset; reject bare timestamps so we never
    # confuse local-time and UTC.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"scheduled_at must include a timezone: {value!r}")
    return dt.astimezone(UTC)


@dataclass
class ScheduledPost:
    id: str
    platform: str
    account_handle: str
    text: str
    scheduled_at_iso: str
    status: ScheduledStatus = "pending"
    media_paths: list[str] = field(default_factory=list)
    created_at_iso: str = field(default_factory=_utcnow_iso)
    note: str = ""  # last error / publish receipt id / cancel reason

    def to_dict(self) -> dict:
        return asdict(self)


class ScheduledPostStore:
    """Append-and-update JSON store. Single-process safe via a lock."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── read ──
    def list_all(
        self,
        *,
        status: ScheduledStatus | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
    ) -> list[ScheduledPost]:
        rows = self._load()
        if status is not None:
            rows = [r for r in rows if r.status == status]
        if start_iso is not None:
            start = _parse_iso(start_iso)
            rows = [r for r in rows if _parse_iso(r.scheduled_at_iso) >= start]
        if end_iso is not None:
            end = _parse_iso(end_iso)
            rows = [r for r in rows if _parse_iso(r.scheduled_at_iso) <= end]
        rows.sort(key=lambda r: r.scheduled_at_iso)
        return rows

    def get(self, post_id: str) -> ScheduledPost | None:
        for r in self._load():
            if r.id == post_id:
                return r
        return None

    def due(self, *, now_iso: str | None = None) -> list[ScheduledPost]:
        """Return pending posts whose scheduled_at is at or before ``now``."""
        cutoff = _parse_iso(now_iso) if now_iso else datetime.now(UTC)
        return [
            r for r in self.list_all(status="pending")
            if _parse_iso(r.scheduled_at_iso) <= cutoff
        ]

    # ── write ──
    def add(
        self,
        *,
        platform: str,
        account_handle: str,
        text: str,
        scheduled_at_iso: str,
        media_paths: list[str] | None = None,
    ) -> ScheduledPost:
        if not platform.strip():
            raise ValueError("scheduled post needs a platform")
        if not account_handle.strip():
            raise ValueError("scheduled post needs an account_handle")
        if not text.strip():
            raise ValueError("scheduled post needs non-empty text")
        scheduled_at = _parse_iso(scheduled_at_iso)  # validates and normalizes
        post = ScheduledPost(
            id=uuid.uuid4().hex[:12],
            platform=platform.strip(),
            account_handle=account_handle.strip(),
            text=text.strip(),
            scheduled_at_iso=scheduled_at.isoformat(timespec="seconds"),
            media_paths=list(media_paths or []),
        )
        with self._lock:
            rows = self._load()
            rows.append(post)
            self._save(rows)
        return post

    def mark(
        self, post_id: str, *, status: ScheduledStatus, note: str = ""
    ) -> ScheduledPost:
        with self._lock:
            rows = self._load()
            for r in rows:
                if r.id == post_id:
                    if r.status != "pending":
                        raise ValueError(
                            f"post {post_id} is {r.status!r}, cannot re-mark"
                        )
                    r.status = status
                    r.note = note
                    self._save(rows)
                    return r
        raise KeyError(f"scheduled post {post_id} not found")

    def cancel(self, post_id: str, *, reason: str = "") -> ScheduledPost:
        return self.mark(post_id, status="cancelled", note=reason)

    # ── disk ──
    def _load(self) -> list[ScheduledPost]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return [ScheduledPost(**row) for row in data]

    def _save(self, rows: list[ScheduledPost]) -> None:
        self.path.write_text(
            json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


@dataclass
class DrainOutcome:
    """Result of one drain pass over the pending queue."""

    enqueued: list[str] = field(default_factory=list)  # post ids → approval queue
    failed: list[tuple[str, str]] = field(default_factory=list)  # (post id, reason)
    skipped_not_due: int = 0

    def as_dict(self) -> dict:
        return {
            "enqueued": list(self.enqueued),
            "failed": [{"id": pid, "reason": r} for pid, r in self.failed],
            "skipped_not_due": self.skipped_not_due,
            "enqueued_count": len(self.enqueued),
            "failed_count": len(self.failed),
        }


def drain_due(
    store: ScheduledPostStore,
    *,
    approvals,  # ApprovalQueue (duck-typed: needs .enqueue(...))
    plan_fn,  # callable matching plan_social_publish signature
    run_id: str = "drain",
    now_iso: str | None = None,
) -> DrainOutcome:
    """Promote due pending posts into the approval queue.

    For each pending post whose ``scheduled_at_iso`` <= now:
      1. Re-validate intent via ``plan_fn`` (typically plan_social_publish).
         If the post text/media no longer validates (e.g. media file was
         deleted), mark the post ``failed`` with the validation reason.
      2. Enqueue a ``send_social`` approval carrying the sha256-intent.
      3. Mark the post ``published`` (the *intent* is published to the
         queue — the operator still resolves before any egress).

    Honest: we do NOT auto-approve. The post moves from "scheduled" to
    "awaiting approval"; if the operator never resolves, no egress.
    """
    outcome = DrainOutcome()
    due = store.due(now_iso=now_iso)
    if not due:
        return outcome

    for post in due:
        try:
            plan = plan_fn(
                platform=post.platform,
                text=post.text,
                account_handle=post.account_handle,
                media_paths=list(post.media_paths),
            )
        except Exception as exc:  # noqa: BLE001 — record reason, continue queue
            with suppress(Exception):
                store.mark(post.id, status="failed", note=str(exc)[:200])
            outcome.failed.append((post.id, str(exc)[:200]))
            continue

        sha = getattr(plan, "sha256_intent", "")
        summary = f"Publish to {post.platform} ({post.account_handle}): {post.text[:120]}"
        payload = {
            "scheduled_post_id": post.id,
            "platform": post.platform,
            "account_handle": post.account_handle,
            "text": post.text,
            "media_paths": list(post.media_paths),
            "sha256_intent": sha,
        }
        try:
            approvals.enqueue(
                run_id=run_id,
                agent="scheduler",
                tool="social.publish",
                action="send_social",
                summary=summary,
                payload=payload,
            )
            store.mark(post.id, status="queued", note=f"sha256:{sha[:12]}")
            outcome.enqueued.append(post.id)
        except Exception as exc:  # noqa: BLE001
            outcome.failed.append((post.id, str(exc)[:200]))

    return outcome
