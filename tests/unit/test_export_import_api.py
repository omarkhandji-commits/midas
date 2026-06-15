"""Sprint 10 — Export/Import + Council dashboard APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.memory import MemoryStore
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
from midas.flagship.market import CompetitorStore
from midas.flagship.schedule import ScheduleStore
from midas.flagship.skills import SkillRegistry


def _build(
    tmp_path: Path,
) -> tuple[TestClient, LoginToken, ApprovalQueue, ReceiptLedger, MemoryStore]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("a7" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    memory = MemoryStore(tmp_path / "memory.db")
    competitors = CompetitorStore(tmp_path / "comp.db")
    schedules = ScheduleStore(tmp_path / "schedules.json")
    registry = SkillRegistry(tmp_path)
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        memory=memory,
        competitors=competitors,
        schedule_store=schedules,
        skill_registry=registry,
    )
    client = TestClient(create_app(deps), base_url="http://testserver")
    return client, token, queue, ledger, memory


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


def test_export_returns_versioned_manifest(tmp_path: Path) -> None:
    client, token, _q, _l, memory = _build(tmp_path)
    _sign_in(client, token)
    from midas.core.memory import MemoryKind

    memory.remember(MemoryKind.BUSINESS, "icp", "agencies")

    r = client.get("/api/export")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == 1
    assert any(e["key"] == "icp" for e in data["memory"])
    assert "competitors" in data
    assert "schedules" in data
    assert "skills" in data


def test_import_queues_approval(tmp_path: Path) -> None:
    client, token, queue, ledger, _m = _build(tmp_path)
    csrf = _sign_in(client, token)

    payload = {
        "version": 1,
        "exported_ts": "2026-06-14T00:00:00Z",
        "memory": [{"key": "k", "content": "c"}],
        "competitors": [],
        "schedules": [],
        "skills": [],
    }
    r = client.post("/api/import", headers=_headers(csrf), json=payload)
    assert r.status_code == 200
    approval_id = r.json()["approval_id"]
    assert any(req.id == approval_id for req in queue.pending())
    decisions = {r.body.decision.value for r in ledger}
    assert "queue_approval" in decisions


def test_import_rejects_wrong_version(tmp_path: Path) -> None:
    client, token, _q, _l, _m = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/import",
        headers=_headers(csrf),
        json={"version": 999},
    )
    assert r.status_code == 400


def test_council_requires_router(tmp_path: Path) -> None:
    client, token, _q, _l, _m = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/council",
        headers=_headers(csrf),
        json={"question": "Should we launch?"},
    )
    assert r.status_code == 503
    assert "router" in r.json()["error"].lower()
