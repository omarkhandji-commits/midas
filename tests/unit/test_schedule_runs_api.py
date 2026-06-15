"""Sprint 8 — Scheduler + Run Manager dashboard APIs."""

from __future__ import annotations

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
from midas.flagship.schedule import ScheduleStore


def _build(tmp_path: Path) -> tuple[TestClient, LoginToken, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("82" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    schedule_store = ScheduleStore(tmp_path / "schedules.json")
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        schedule_store=schedule_store,
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
    assert r.status_code == 303
    return r.cookies[CSRF_COOKIE]


def _headers(csrf: str) -> dict[str, str]:
    return {"origin": "http://testserver", "x-midas-csrf": csrf}


def test_schedule_add_list_delete_roundtrip(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    csrf = _sign_in(client, token)

    listing = client.get("/api/schedules").json()
    assert listing["schedules"] == []

    add = client.post(
        "/api/schedules",
        headers=_headers(csrf),
        json={"name": "daily-seo", "niche": "local SEO", "at": "09:00", "mode": "deep"},
    )
    assert add.status_code == 200
    recipe = add.json()["recipe"]
    assert recipe["cadence"] == "daily"
    assert "midas scan" in recipe["command"]
    assert "schtasks" in recipe["windows_task"]
    assert "cron" in recipe["github_actions"]

    listing = client.get("/api/schedules").json()
    assert len(listing["schedules"]) == 1

    removed = client.delete("/api/schedules/daily-seo", headers=_headers(csrf))
    assert removed.status_code == 200
    assert client.get("/api/schedules").json()["schedules"] == []

    tools = {r.body.tool for r in ledger}
    assert "schedule.add" in tools
    assert "schedule.delete" in tools


def test_schedule_add_rejects_bad_time_format(tmp_path: Path) -> None:
    client, token, _l = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post(
        "/api/schedules",
        headers=_headers(csrf),
        json={"name": "x", "niche": "y", "at": "9am"},
    )
    assert r.status_code == 400


def test_schedule_delete_unknown_returns_404(tmp_path: Path) -> None:
    client, token, _l = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.delete("/api/schedules/none", headers=_headers(csrf))
    assert r.status_code == 404


def test_runs_endpoint_reports_status_per_run_id(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    _sign_in(client, token)
    ledger.append(
        run_id="run-ok",
        agent="cli",
        tool="setup",
        decision=Decision.ALLOW,
        inputs={},
        outputs={},
    )
    ledger.append(
        run_id="run-pending",
        agent="cli",
        tool="approval.enqueue",
        decision=Decision.QUEUE_APPROVAL,
        inputs={},
        outputs={},
    )
    ledger.append(
        run_id="run-denied",
        agent="sentinel",
        tool="email.send",
        decision=Decision.DENY,
        inputs={},
        outputs={},
    )
    r = client.get("/api/runs").json()
    by_id = {row["run_id"]: row for row in r["runs"]}
    assert by_id["run-ok"]["status"] == "ok"
    assert by_id["run-pending"]["status"] == "awaiting_approval"
    assert by_id["run-denied"]["status"] == "denied"
    assert "cli" in by_id["run-ok"]["agents"]
