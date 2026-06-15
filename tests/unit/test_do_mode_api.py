"""Sprint F1 — Do-mode SSE + /api/execute endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals.queue import ApprovalQueue, ApprovalStatus
from midas.core.config.models import (
    ActionsPolicy,
    ApprovalPolicy,
    AuditPolicy,
    FilesystemPolicy,
    ModelsPolicy,
    PolicyConfig,
    SourcesPolicy,
    SpendCaps,
)
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel import Sentinel
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write", "execute_code", "write_spreadsheet"},
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


def _build(tmp_path: Path) -> tuple[TestClient, LoginToken, ApprovalQueue, ReceiptLedger, Path]:
    state = tmp_path / ".midas"
    state.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    token = LoginToken()
    ledger = ReceiptLedger(state / "r.jsonl", Signer.from_hex_seed("f1" * 32))
    queue = ApprovalQueue(state / "apv.db", ledger=ledger)
    guard = FsGuard(workspace=workspace.resolve())
    sentinel = Sentinel(_policy())
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        sentinel=sentinel,
        fs_guard=guard,
        # Router=None: Do mode falls back to artifact.text refuse-planner.
    )
    client = TestClient(create_app(deps), base_url="http://testserver")
    return client, token, queue, ledger, workspace


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    return r.cookies[CSRF_COOKIE]


def _h(csrf: str) -> dict[str, str]:
    return {"origin": "http://testserver", "x-midas-csrf": csrf}


def test_do_mode_streams_step_and_approval_events(tmp_path: Path) -> None:
    client, token, queue, _, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    with client.stream(
        "POST",
        "/api/chat",
        headers=_h(csrf),
        json={"message": "draft a note", "mode": "do"},
    ) as r:
        body = r.read().decode("utf-8")
    # Without a router the fallback planner asks for artifact.text → APPROVE-tier → queued.
    assert "event: start" in body
    assert "event: step" in body
    assert "artifact.text" in body
    assert "event: approval" in body
    assert "event: done" in body
    # The approval was queued in the same queue the rest of the dashboard uses.
    assert any(req.tool == "artifact.text" for req in queue.pending())


def test_do_mode_rejects_invalid_mode(tmp_path: Path) -> None:
    client, token, _, _, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/chat", headers=_h(csrf), json={"message": "x", "mode": "wat"}
    )
    assert r.status_code == 400


def test_execute_writes_file_after_approval(tmp_path: Path) -> None:
    client, token, queue, ledger, workspace = _build(tmp_path)
    csrf = _sign_in(client, token)

    # Drive a Do-mode run to queue an approval.
    with client.stream(
        "POST",
        "/api/chat",
        headers=_h(csrf),
        json={"message": "do something", "mode": "do"},
    ) as r:
        r.read()

    pending = queue.pending()
    assert pending, "Do mode must queue an approval"
    apv = pending[0]
    queue.approve(apv.id, by="test")
    assert queue.get(apv.id).status == ApprovalStatus.APPROVED

    # Execute it from the dashboard.
    r = client.post(f"/api/execute/{apv.id}", headers=_h(csrf))
    assert r.status_code == 200
    result = r.json()["result"]
    assert "path" in result
    # File materialized inside the workspace.
    assert Path(result["path"]).exists()
    # An executed-receipt was written.
    tools = {receipt.body.tool for receipt in ledger}
    assert any(t.endswith(".executed") for t in tools)


def test_execute_rejects_non_approved(tmp_path: Path) -> None:
    client, token, queue, _, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    with client.stream(
        "POST",
        "/api/chat",
        headers=_h(csrf),
        json={"message": "x", "mode": "do"},
    ) as r:
        r.read()
    apv = queue.pending()[0]
    r = client.post(f"/api/execute/{apv.id}", headers=_h(csrf))
    assert r.status_code == 409


def test_execute_404_on_unknown_id(tmp_path: Path) -> None:
    client, token, _, _, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post("/api/execute/9999", headers=_h(csrf))
    assert r.status_code == 404


def test_chat_mode_backward_compatible(tmp_path: Path) -> None:
    """Without an LLM router, chat mode returns 503 — but the request must still parse."""
    client, token, _, _, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/chat", headers=_h(csrf), json={"message": "hi"}
    )
    # No router on deps → chat path returns 503; the point is the new mode field
    # is optional and the existing chat-mode entry still works.
    assert r.status_code == 503
