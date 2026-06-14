"""SSE events: snapshot shape, change-only emission, owner gating, no PII leakage."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE
from midas.flagship.dashboard.events import Snapshot, event_stream, take_snapshot


def _ledger(tmp_path: Path) -> ReceiptLedger:
    return ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("aa" * 32))


def _queue(tmp_path: Path) -> ApprovalQueue:
    return ApprovalQueue(tmp_path / "apv.db")


# ── pure-logic ────────────────────────────────────────────────────────────────
def test_snapshot_to_event_is_compact_no_pii(tmp_path: Path) -> None:
    snap = Snapshot(spent_usd=0.12345, receipt_count=3, pending_count=1)
    frame = snap.to_event()
    # SSE wire format requires `event:` + `data:` + a trailing blank line.
    assert frame.startswith("event: tick\n")
    assert frame.endswith("\n\n")
    data = json.loads(frame.split("data: ", 1)[1].strip())
    # Only the three numeric fields — never message bodies, never secrets.
    assert set(data) == {"spent_usd", "receipts", "pending"}
    assert data["spent_usd"] == 0.12345


def test_take_snapshot_sums_costs_and_counts(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    queue = _queue(tmp_path)
    for c in (0.01, 0.02):
        ledger.append(run_id="r", agent="a", tool="t", decision=Decision.ALLOW,
                      inputs={}, outputs={}, cost_usd=c)
    queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    snap = take_snapshot(queue=queue, ledger=ledger)
    assert abs(snap.spent_usd - 0.03) < 1e-9
    assert snap.receipt_count == 2
    assert snap.pending_count == 1


def test_event_stream_only_emits_on_change(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    queue = _queue(tmp_path)

    async def run():
        # 3 ticks with no state change → exactly 1 frame (the initial snapshot).
        frames: list[str] = []
        async for f in event_stream(
            queue=queue, ledger=ledger, interval_seconds=0, max_ticks=3
        ):
            frames.append(f)
        return frames

    frames = asyncio.run(run())
    assert len(frames) == 1, frames


# ── HTTP integration ──────────────────────────────────────────────────────────
def _client(tmp_path: Path) -> tuple[TestClient, ApprovalQueue, ReceiptLedger, LoginToken]:
    ledger = _ledger(tmp_path)
    queue = _queue(tmp_path)
    sessions = Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key()))
    token = LoginToken()
    deps = DashboardDeps(
        queue=queue, sessions=sessions, login_token=token,
        allowed_hosts={"testserver"}, ledger=ledger, sse_interval_seconds=0,
    )
    return TestClient(create_app(deps), base_url="http://testserver"), queue, ledger, token


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login", data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"}, follow_redirects=False,
    )
    return r.cookies[CSRF_COOKIE]


def test_events_requires_session(tmp_path: Path) -> None:
    client, _, _, _ = _client(tmp_path)
    r = client.get("/events")
    assert r.status_code == 401


def test_snapshot_endpoint(tmp_path: Path) -> None:
    client, queue, ledger, token = _client(tmp_path)
    ledger.append(run_id="r", agent="a", tool="t", decision=Decision.ALLOW,
                  inputs={}, outputs={}, cost_usd=0.05)
    queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    _sign_in(client, token)
    r = client.get("/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert abs(body["spent_usd"] - 0.05) < 1e-9
    assert body["receipts"] == 1 and body["pending"] == 1
