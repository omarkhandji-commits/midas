"""Dashboard missions/assets/proof APIs."""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.memory import MemoryStore
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


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken, ApprovalQueue, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("56" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        memory=MemoryStore(tmp_path / "memory.db"),
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token, queue, ledger


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return r.cookies[CSRF_COOKIE]


def test_mission_scan_returns_move_assets_and_approval(tmp_path: Path) -> None:
    client, token, queue, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/missions",
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
        json={"niche": "local SEO agency", "mode": "deep"},
    )

    assert r.status_code == 200
    mission = r.json()["mission"]
    assert mission["daily_move"]["name"]
    assert "offer" in mission["daily_move"]["assets"]
    assert mission["approval_id"] is not None
    assert queue.pending()[0].action == "send_email"
    assert any(receipt.body.tool == "missions.scan" for receipt in ledger)


def test_assets_generate_returns_real_pdf_payloads(tmp_path: Path) -> None:
    client, token, _queue, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/assets/generate",
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
        json={"topic": "Proof-first audit", "summary": "Validate a market before outreach."},
    )

    assert r.status_code == 200
    body = r.json()
    assert "outreach_email" in body["assets"]
    proposal = base64.b64decode(body["pdfs"]["proposal_pdf"]["base64"])
    assert proposal.startswith(b"%PDF-1.4")
    assert any(receipt.body.tool == "assets.generate" for receipt in ledger)


def test_proof_ledger_reports_chain_status(tmp_path: Path) -> None:
    client, token, _queue, ledger = _client(tmp_path)
    ledger.append(run_id="r", agent="a", tool="t", decision=Decision.ALLOW, inputs={}, outputs={})
    _sign_in(client, token)

    r = client.get("/api/proofs")

    assert r.status_code == 200
    assert r.json()["chain"]["ok"] is True
    assert r.json()["chain"]["count"] == 1
