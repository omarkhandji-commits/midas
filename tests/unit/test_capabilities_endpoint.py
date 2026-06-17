"""/api/capabilities — single source of truth for the Capabilities page.

The endpoint reflects the registered toolset, so adding a new tool in
``registry.py`` makes it appear in the UI without touching the front end.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.config.models import (
    ActionsPolicy,
    PolicyConfig,
    SpendCaps,
)
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel.gate import Sentinel
from midas.flagship.agent import FsGuard
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)


def _policy() -> PolicyConfig:
    return PolicyConfig(
        spend_caps=SpendCaps(per_task=0.25, daily=2.0, monthly=30.0),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write", "execute_code", "write_spreadsheet"},
            never={"spam", "leak_secret"},
        ),
    )


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("12" * 32))
    policy = _policy()
    deps = DashboardDeps(
        queue=ApprovalQueue(tmp_path / "apv.db"),
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        sentinel=Sentinel(policy),
        fs_guard=FsGuard.from_policy(tmp_path, policy.filesystem),
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token


def _sign_in(client: TestClient, token: LoginToken) -> None:
    r = client.get(f"/login?token={token.value}", follow_redirects=False)
    assert r.status_code == 303


def test_capabilities_returns_registered_tools(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    _sign_in(client, token)

    r = client.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    names = {t["name"] for t in body["tools"]}
    # Sample of tools from the actual registry — if these disappear we want to know.
    assert "fs.read" in names
    assert "fs.write" in names
    assert "landing.draft" in names
    assert "code.run" in names

    fs_read = next(t for t in body["tools"] if t["name"] == "fs.read")
    assert fs_read["tier"] == "auto"
    assert fs_read["group"] == "Files"

    fs_write = next(t for t in body["tools"] if t["name"] == "fs.write")
    assert fs_write["tier"] == "approve"  # repo_write is in requires_approval
    assert fs_write["group"] == "Files"

    landing = next(t for t in body["tools"] if t["name"] == "landing.draft")
    assert landing["group"] == "Cash artifacts"


def test_capabilities_requires_session(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/api/capabilities").status_code == 401
