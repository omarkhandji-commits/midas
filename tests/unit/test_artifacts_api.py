"""Sprint F1 — /api/artifacts lists executed artifact receipts."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals.queue import ApprovalQueue
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


def _build(tmp_path: Path) -> tuple[TestClient, LoginToken, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f1" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
    )
    client = TestClient(create_app(deps), base_url="http://testserver")
    return client, token, ledger


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    return r.cookies[CSRF_COOKIE]


def test_artifacts_empty_when_nothing_executed(tmp_path: Path) -> None:
    client, token, _ = _build(tmp_path)
    _sign_in(client, token)
    r = client.get("/api/artifacts")
    assert r.status_code == 200
    assert r.json() == {"artifacts": []}


def test_artifacts_returns_executed_receipts_only(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    _sign_in(client, token)
    # Non-artifact receipt (planning step) — must NOT appear.
    ledger.append(
        run_id="r-1", agent="a", tool="fs.read",
        decision=Decision.ALLOW, inputs={}, outputs={},
    )
    # Two executed artifact receipts — must appear newest first.
    ledger.append(
        run_id="r-1", agent="execute", tool="fs.write.executed",
        decision=Decision.ALLOW,
        inputs={"path": "out.txt"},
        outputs={"path": "out.txt", "bytes": 4, "sha256_new": "a" * 64},
    )
    ledger.append(
        run_id="r-2", agent="execute", tool="email.draft.executed",
        decision=Decision.ALLOW,
        inputs={"path": "d.eml"},
        outputs={"path": "d.eml", "sha256_new": "b" * 64},
    )

    data = client.get("/api/artifacts").json()
    assert len(data["artifacts"]) == 2
    # Newest first.
    assert data["artifacts"][0]["kind"] == "email.draft"
    assert data["artifacts"][1]["kind"] == "fs.write"
    # Hash + run_id surfaced for verification linkage.
    assert all(a["hash"] for a in data["artifacts"])
    assert all(a["run_id"] for a in data["artifacts"])
