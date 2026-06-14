"""SPA serving contract — the React shell is served when present, never otherwise.

Pins Sprint-0 behavior so any regression (CSP, route ordering, catch-all leakage)
is caught immediately. The built SPA is fixture-faked: we drop a tiny `index.html`
on disk for the duration of the test, then remove it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
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
from midas.flagship.dashboard import app as dashboard_app
from midas.flagship.market import CompetitorStore

SPA_BODY = (
    "<!doctype html><html><head><title>MIDAS SPA</title></head>"
    "<body><div id=root></div></body></html>"
)


@pytest.fixture()
def spa_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Drop a tiny index.html at the real on-disk SPA location for the test."""
    real = dashboard_app._SPA_INDEX
    real.parent.mkdir(parents=True, exist_ok=True)
    pre_existing = real.exists()
    backup = real.read_text(encoding="utf-8") if pre_existing else None
    real.write_text(SPA_BODY, encoding="utf-8")
    yield real
    if pre_existing and backup is not None:
        real.write_text(backup, encoding="utf-8")
    else:
        real.unlink(missing_ok=True)


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken]:
    queue = ApprovalQueue(tmp_path / "apv.db")
    memory = MemoryStore(tmp_path / "memory.db")
    competitors = CompetitorStore(tmp_path / "market.db")
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("cd" * 32))
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
    return TestClient(create_app(deps), base_url="http://testserver"), token


def _sign_in(client: TestClient, token: LoginToken) -> None:
    client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )


def test_spa_served_at_root_when_built(tmp_path: Path, spa_index: Path) -> None:
    """`/` returns the SPA index for an authenticated owner once the build is present."""
    client, token = _client(tmp_path)
    _sign_in(client, token)
    r = client.get("/")
    assert r.status_code == 200
    assert "MIDAS SPA" in r.text


def test_spa_route_serves_index_for_client_routes(tmp_path: Path, spa_index: Path) -> None:
    """React Router owns the routes — `/missions`, `/providers`, etc. all return the SPA shell."""
    client, token = _client(tmp_path)
    _sign_in(client, token)
    for route in ("missions", "providers", "channels", "memory", "settings"):
        r = client.get(f"/{route}")
        assert r.status_code == 200, route
        assert "MIDAS SPA" in r.text


def test_spa_route_requires_session(tmp_path: Path, spa_index: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.get("/missions")
    assert r.status_code == 401


def test_spa_catchall_never_swallows_api_or_docs(tmp_path: Path, spa_index: Path) -> None:
    """Auto-disabled FastAPI doc paths stay 404 — no fingerprinting."""
    client, token = _client(tmp_path)
    _sign_in(client, token)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
    # `/api/missing` is genuinely a 404 (no such API), not a SPA route.
    assert client.get("/api/this-does-not-exist").status_code == 404


def test_falls_back_to_jinja_when_spa_not_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No build on disk → the legacy server-rendered console keeps working.

    We monkeypatch `_spa_available` rather than removing the real file, so a
    parallel `npm run build` checkout isn't corrupted by this test.
    """
    monkeypatch.setattr(dashboard_app, "_spa_available", lambda: False)
    client, token = _client(tmp_path)
    _sign_in(client, token)
    r = client.get("/")
    assert r.status_code == 200
    assert "Local dashboard only" in r.text
