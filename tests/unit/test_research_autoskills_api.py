"""Audit gap closure — dashboard endpoints for research + auto-skills."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision, Taint
from midas.core.web import StaticFetcher, StaticSearchAdapter
from midas.core.web.search import SearchHit
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


def _build(tmp_path: Path) -> tuple[TestClient, LoginToken, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("c3" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    registry = SkillRegistry(tmp_path)
    search = StaticSearchAdapter([
        SearchHit(title="A", url="https://a.example/p"),
        SearchHit(title="B", url="https://b.example/p"),
    ])
    fetcher = StaticFetcher({
        "https://a.example/p": "content one",
        "https://b.example/p": "content two",
    })
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        skill_registry=registry,
        search=search,
        fetcher=fetcher,
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


def _h(csrf: str) -> dict[str, str]:
    return {"origin": "http://testserver", "x-midas-csrf": csrf}


def test_research_returns_cited_result(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post("/api/research", headers=_h(csrf), json={"question": "what is x", "k": 2})
    assert r.status_code == 200
    data = r.json()["result"]
    assert data["query"] == "what is x"
    assert data["proof_level"] in {"high", "medium", "low"}
    assert len(data["sources"]) == 2
    tools = {r.body.tool for r in ledger}
    assert "research.run" in tools


def test_research_requires_question(tmp_path: Path) -> None:
    client, token, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post("/api/research", headers=_h(csrf), json={})
    assert r.status_code == 400


def test_autoskills_lists_pending_after_detection(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    _sign_in(client, token)
    # Seed a 3-step local run
    for tool in ("research.search", "research.fetch", "research.summarize"):
        ledger.append(
            run_id="ui-run",
            agent="r",
            tool=tool,
            decision=Decision.ALLOW,
            inputs={},
            outputs={},
            taint_in=Taint.TRUSTED,
            taint_out=Taint.TRUSTED,
        )
    r = client.get("/api/autoskills")
    assert r.status_code == 200
    proposals = r.json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["local_only"] is True


def test_autoskills_accept_then_discard_flow(tmp_path: Path) -> None:
    client, token, ledger = _build(tmp_path)
    csrf = _sign_in(client, token)
    for tool in ("a.x", "a.y", "a.z"):
        ledger.append(run_id="ui-run", agent="r", tool=tool,
                      decision=Decision.ALLOW, inputs={}, outputs={})

    listing = client.get("/api/autoskills").json()["proposals"]
    pid = listing[0]["proposal_id"]
    accept = client.post(f"/api/autoskills/{pid}/accept", headers=_h(csrf))
    assert accept.status_code == 200
    assert accept.json()["skill"]["name"]

    # Now lists should be empty (accepted, not pending)
    after = client.get("/api/autoskills").json()["proposals"]
    assert after == []

    # Discard an unknown id returns 404
    bad = client.post("/api/autoskills/nope/discard", headers=_h(csrf), json={"reason": "x"})
    assert bad.status_code == 404


def test_autoskills_accept_unknown_returns_404(tmp_path: Path) -> None:
    client, token, _ = _build(tmp_path)
    csrf = _sign_in(client, token)
    r = client.post("/api/autoskills/missing/accept", headers=_h(csrf))
    assert r.status_code == 404
