"""Outcome ingestion: persists to memory, writes a receipt, refuses bad input."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.memory import MemoryKind, MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE
from midas.flagship.outcomes import Outcome, ingest_outcome, summarize_history


# ── unit ──────────────────────────────────────────────────────────────────────
def test_outcome_empty_key_rejected(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    with pytest.raises(ValueError, match="move_key"):
        ingest_outcome(Outcome(move_key="   ", outcome="x"), memory=mem)


def test_unsourced_outcome_is_low_proof(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    entry = ingest_outcome(
        Outcome(move_key="launch1", outcome="3 signups", metrics={"signups": 3}),
        memory=mem,
    )
    from midas.core.agents.summary import ProofLevel
    assert entry.proof_level == ProofLevel.LOW  # no source → never MEDIUM/HIGH


def test_sourced_outcome_lifts_to_medium(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    entry = ingest_outcome(
        Outcome(
            move_key="launch1", outcome="3 signups",
            metrics={"clicks": 120}, sources=["dash.local/analytics"],
        ),
        memory=mem,
    )
    from midas.core.agents.summary import ProofLevel
    assert entry.proof_level == ProofLevel.MEDIUM


def test_ingest_writes_receipt_without_pii(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("bb" * 32))
    ingest_outcome(
        Outcome(move_key="m1", outcome="some sensitive narrative",
                metrics={"sales": 1}, sources=["x"]),
        memory=mem, ledger=ledger, run_id="run1",
    )
    last = list(ledger)[-1]
    assert last.body.tool == "record_result"
    # The narrative must not appear in the receipt — only structural fields.
    raw = (tmp_path / "r.jsonl").read_text(encoding="utf-8")
    assert "sensitive narrative" not in raw


def test_summarize_history_returns_latest_proof(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    ingest_outcome(Outcome(move_key="m1", outcome="v1"), memory=mem)
    ingest_outcome(
        Outcome(move_key="m1", outcome="v2 sourced", sources=["a"]), memory=mem,
    )
    summary = summarize_history(mem, "m1")
    assert summary["count"] == 1  # supersede behavior: only the live row counts
    assert "v2" in summary["latest"]
    assert summary["proof"] == "medium"


# ── HTTP integration ──────────────────────────────────────────────────────────
def _client(tmp_path: Path):
    mem = MemoryStore(tmp_path / "m.db")
    queue = ApprovalQueue(tmp_path / "apv.db")
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("cc" * 32))
    sessions = Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key()))
    token = LoginToken()
    deps = DashboardDeps(
        queue=queue, sessions=sessions, login_token=token,
        allowed_hosts={"testserver"}, ledger=ledger, memory=mem,
    )
    return TestClient(create_app(deps), base_url="http://testserver"), mem, token


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login", data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"}, follow_redirects=False,
    )
    return r.cookies[CSRF_COOKIE]


def test_outcomes_requires_session_and_csrf(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    # No matching CSRF cookie → middleware refuses BEFORE the handler runs (403).
    # This is the correct order: layered defense rejects at the earliest gate.
    r = client.post(
        "/outcomes", json={"move_key": "m1", "outcome": "x"},
        headers={"origin": "http://testserver", "x-midas-csrf": "x"},
    )
    assert r.status_code == 403


def test_outcomes_records_via_api(tmp_path: Path) -> None:
    client, mem, token = _client(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/outcomes",
        json={"move_key": "m1", "outcome": "3 replies",
              "metrics": {"replies": 3}, "sources": ["crm.local/x"]},
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["proof_level"] == "medium"
    recalled = mem.recall(kind=MemoryKind.RESULT, query="m1")
    assert recalled and "3 replies" in recalled[0].content


def test_outcomes_bad_payload_400(tmp_path: Path) -> None:
    client, _, token = _client(tmp_path)
    csrf = _sign_in(client, token)
    # Missing required `outcome` field → 400, never 500.
    r = client.post(
        "/outcomes", json={"move_key": "m1"},
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
    )
    assert r.status_code == 400
