"""Dashboard API surface for the Operator Console."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.memory import MemoryKind, MemoryStore
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
from midas.flagship.market import CompetitorStore


def _client(tmp_path: Path):
    queue = ApprovalQueue(tmp_path / "apv.db")
    memory = MemoryStore(tmp_path / "memory.db")
    competitors = CompetitorStore(tmp_path / "market.db")
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("ab" * 32))
    token = LoginToken()
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        memory=memory,
        competitors=competitors,
    )
    return (
        TestClient(create_app(deps), base_url="http://testserver"),
        token,
        queue,
        memory,
        competitors,
        ledger,
    )


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    return r.cookies[CSRF_COOKIE]


def test_dashboard_api_returns_product_surfaces(tmp_path: Path) -> None:
    client, token, queue, memory, competitors, ledger = _client(tmp_path)
    queue.enqueue(run_id="r", agent="a", tool="email", action="external_send", summary="x")
    memory.remember(MemoryKind.BUSINESS, "offer", "SEO audit offer")
    competitors.add("Acme", "https://acme.example")
    ledger.append(run_id="r", agent="a", tool="t", decision=Decision.ALLOW, inputs={}, outputs={})
    _sign_in(client, token)

    assert client.get("/api/approvals").json()["pending"][0]["action"] == "external_send"
    assert client.get("/api/memory/search?q=SEO").json()["memory"][0]["key"] == "offer"
    assert client.get("/api/competitors").json()["competitors"][0]["name"] == "Acme"
    assert client.get("/api/proofs").json()["proofs"][0]["tool"] == "t"
    assert "proposal_pdf" in client.get("/api/assets").json()["asset_types"]
