"""Server-Sent Events stream — live cost + queue depth, owner-only.

Why SSE not WebSocket: one-way push fits the use case, plays nice with proxies, and
keeps the security model simple (same Origin + cookie auth as the rest of the app).

The stream is owner-only (session-gated) and bound to the same allow-listed Origin.
Each snapshot is computed locally — no external network. We poll the backing stores
on a short interval because both `ApprovalQueue` and `ReceiptLedger` are append-only
SQLite/JSONL, where a tiny scan is cheaper than wiring a change-notifier through
sqlite triggers.

We never push secrets, message contents, or PII over SSE — only the small numeric
shape the operator needs to feel the system breathing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Snapshot:
    """The tiny number triple that drives the live header."""

    spent_usd: float
    receipt_count: int
    pending_count: int

    def to_event(self) -> str:
        """SSE wire format: `event:` + `data:` + blank line. No HTML, no PII."""
        body = json.dumps(
            {
                "spent_usd": round(self.spent_usd, 6),
                "receipts": self.receipt_count,
                "pending": self.pending_count,
            },
            separators=(",", ":"),  # compact; no whitespace leak
        )
        return f"event: tick\ndata: {body}\n\n"


def take_snapshot(*, queue: Any, ledger: Any) -> Snapshot:
    receipts = list(ledger) if ledger is not None else []
    spent = sum(r.body.cost_usd for r in receipts)
    pending = len(queue.pending()) if queue is not None else 0
    return Snapshot(spent_usd=spent, receipt_count=len(receipts), pending_count=pending)


async def event_stream(
    *,
    queue: Any,
    ledger: Any,
    interval_seconds: float = 1.5,
    max_ticks: int | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames until the client disconnects. `max_ticks` is for tests only."""
    last: Snapshot | None = None
    count = 0
    while True:
        snap = take_snapshot(queue=queue, ledger=ledger)
        # Only push on change → minimal bytes on the wire, less render churn in the UI.
        if snap != last:
            yield snap.to_event()
            last = snap
        count += 1
        if max_ticks is not None and count >= max_ticks:
            return
        await asyncio.sleep(interval_seconds)
