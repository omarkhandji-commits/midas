"""Sprint 9 — Skills + Multimodal dashboard APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
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
from midas.flagship.skills import SkillRegistry


def _build(
    tmp_path: Path,
) -> tuple[TestClient, LoginToken, ApprovalQueue, ReceiptLedger, SkillRegistry]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("91" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    registry = SkillRegistry(tmp_path)
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        skill_registry=registry,
    )
    client = TestClient(create_app(deps), base_url="http://testserver")
    return client, token, queue, ledger, registry


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


def _headers(csrf: str) -> dict[str, str]:
    return {"origin": "http://testserver", "x-midas-csrf": csrf}


def test_skills_create_list_delete_roundtrip(tmp_path: Path) -> None:
    client, token, _queue, ledger, _reg = _build(tmp_path)
    csrf = _sign_in(client, token)

    create = client.post(
        "/api/skills",
        headers=_headers(csrf),
        json={"name": "market-radar-pro", "summary": "Watch competitors."},
    )
    assert create.status_code == 200
    assert create.json()["skill"]["name"] == "market-radar-pro"

    listing = client.get("/api/skills").json()
    assert any(s["name"] == "market-radar-pro" for s in listing["skills"])

    removed = client.delete(
        "/api/skills/market-radar-pro", headers=_headers(csrf)
    )
    assert removed.status_code == 200
    assert client.get("/api/skills").json()["skills"] == []
    tools = {r.body.tool for r in ledger}
    assert "skills.create" in tools
    assert "skills.delete" in tools


def test_skills_plan_download_queues_approval(tmp_path: Path) -> None:
    client, token, queue, ledger, _reg = _build(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/skills/plan-download",
        headers=_headers(csrf),
        json={"url": "https://github.com/example/skill.git", "reason": "research"},
    )
    assert r.status_code == 200
    approval_id = r.json()["approval_id"]
    assert approval_id is not None
    pending = queue.pending()
    assert any(req.id == approval_id for req in pending)
    decisions = {r.body.decision.value for r in ledger}
    assert "queue_approval" in decisions


def test_skills_plan_download_rejects_non_remote(tmp_path: Path) -> None:
    client, token, _q, _l, _r = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/skills/plan-download",
        headers=_headers(csrf),
        json={"url": "/local/path/skill"},
    )
    assert r.status_code == 400


def test_multimodal_inspect_text_file(tmp_path: Path) -> None:
    client, token, _q, ledger, _r = _build(tmp_path)
    csrf = _sign_in(client, token)
    target = tmp_path / "note.md"
    target.write_text("# Hello\nContent.", encoding="utf-8")

    r = client.post(
        "/api/multimodal/inspect",
        headers=_headers(csrf),
        json={"path": str(target)},
    )
    assert r.status_code == 200
    media = r.json()["media"]
    assert media["kind"] == "text"
    assert "Hello" in media["text"]
    assert media["sha256"]
    assert any(r.body.tool == "multimodal.inspect" for r in ledger)


def test_multimodal_inspect_rejects_missing(tmp_path: Path) -> None:
    client, token, _q, _l, _r = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/multimodal/inspect",
        headers=_headers(csrf),
        json={"path": str(tmp_path / "nope.txt")},
    )
    assert r.status_code == 400
