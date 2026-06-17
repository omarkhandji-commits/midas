"""Magic-link login: GET /login?token=… signs the user in once.

This is what makes ``midas init`` open the browser already authenticated, with
zero copy-paste. The same constant-time, single-use token used by the POST form
is consumed here too — so a stolen link is worthless after one click.
"""

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
from midas.flagship.dashboard.app import SESSION_COOKIE


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("12" * 32))
    deps = DashboardDeps(
        queue=ApprovalQueue(tmp_path / "apv.db"),
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token


def test_magic_link_signs_in_once(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    value = token.value

    r = client.get(f"/login?token={value}", follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert SESSION_COOKIE in r.cookies


def test_magic_link_is_single_use(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    value = token.value

    first = client.get(f"/login?token={value}", follow_redirects=False)
    assert first.status_code == 303

    second = client.get(f"/login?token={value}", follow_redirects=False)
    assert second.status_code == 401
    assert SESSION_COOKIE not in second.cookies


def test_magic_link_wrong_token_shows_form(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    r = client.get("/login?token=not-the-right-thing", follow_redirects=False)

    assert r.status_code == 401
    assert SESSION_COOKIE not in r.cookies
    # The legacy POST form is still rendered so the user can recover.
    assert b"One-time token" in r.content


def test_login_without_token_still_renders_form(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    r = client.get("/login")

    assert r.status_code == 200
    assert b"One-time token" in r.content
