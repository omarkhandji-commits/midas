"""Approval queue: enqueue/resolve, idempotency, owner gating, timeout, toolset wiring."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from midas.core.agents import Tool, Toolset
from midas.core.approvals import ApprovalError, ApprovalQueue, ApprovalStatus
from midas.core.config import load_policy
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel import Sentinel

BASE = Path(__file__).resolve().parents[2]


def _queue(tmp_path: Path, **kw) -> ApprovalQueue:
    return ApprovalQueue(tmp_path / "apv.db", **kw)


def test_enqueue_then_approve(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    req = q.enqueue(
        run_id="r1", agent="ops", tool="email", action="send_email",
        summary="send launch", payload={"to": "a@b.com"},
    )
    assert q.pending() and q.pending()[0].id == req.id
    out = q.approve(req.id, by="owner")
    assert out.status == ApprovalStatus.APPROVED
    assert q.pending() == []


def test_reject_closes_request(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    out = q.reject(req.id, by="owner", note="not yet")
    assert out.status == ApprovalStatus.REJECTED
    assert out.note == "not yet"


def test_double_resolve_is_rejected(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    q.approve(req.id, by="owner")
    with pytest.raises(ApprovalError, match="already"):
        q.approve(req.id, by="owner")  # idempotency: a second resolve must not fire
    with pytest.raises(ApprovalError):
        q.reject(req.id, by="owner")


def test_owner_id_gate(tmp_path: Path) -> None:
    q = _queue(tmp_path, owner_ids={"omar"})
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    with pytest.raises(ApprovalError, match="not authorized"):
        q.approve(req.id, by="random_stranger")
    q.approve(req.id, by="omar")  # ok


def test_expire_pending(tmp_path: Path) -> None:
    q = _queue(tmp_path)
    # Backdate created_ts manually to bypass clock dependencies.
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    old = "1970-01-01T00:00:00+00:00"
    q._conn.execute("UPDATE approvals SET created_ts=? WHERE id=?", (old, req.id))
    q._conn.commit()
    n = q.expire_pending(older_than=timedelta(hours=1))
    assert n == 1
    assert q.get(req.id).status == ApprovalStatus.EXPIRED


def test_resolve_writes_receipt(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("ee" * 32))
    q = _queue(tmp_path, ledger=ledger)
    req = q.enqueue(run_id="r1", agent="ops", tool="email", action="send_email", summary="x")
    q.approve(req.id, by="owner", note="ok")
    last = list(ledger)[-1]
    assert last.body.tool == "email"
    assert last.body.approval_id == str(req.id)


# ── toolset wiring: QUEUE_APPROVAL parks the call ────────────────────────────
def test_toolset_parks_approval_in_queue(tmp_path: Path) -> None:
    policy = load_policy(BASE / "config" / "policy.yml")
    q = ApprovalQueue(tmp_path / "apv.db")
    ts = Toolset(Sentinel(policy), approvals=q)
    fired = []
    ts.register(Tool("email", action="send_email", fn=lambda **k: fired.append(1)))
    out = ts.invoke("email", to="a@b.com")
    assert out.ran is False  # parked, not fired
    assert out.approval_id is not None
    assert fired == []
    parked = q.pending()
    assert len(parked) == 1
    assert parked[0].tool == "email" and parked[0].payload == {"to": "a@b.com"}
