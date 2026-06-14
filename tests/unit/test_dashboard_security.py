"""Dashboard HTTP-level defenses: CSP, CSRF, Origin, loopback bind, headers, app flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    RateLimiter,
    SessionConfig,
    Sessions,
    create_app,
    csrf_ok,
    generate_secret_key,
    origin_ok,
    security_headers,
)
from midas.flagship.dashboard.app import CSRF_COOKIE, SESSION_COOKIE


# ── pure-logic helpers ───────────────────────────────────────────────────────
def test_security_headers_are_strict() -> None:
    h = security_headers(nonce="abc")
    csp = h["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    # Script-src must stay locked: no inline scripts, only own bundles + nonce.
    script_src = _csp_directive(csp, "script-src")
    assert "'unsafe-inline'" not in script_src
    assert "'nonce-" in script_src
    # Style-src concedes 'unsafe-inline' for Radix/shadcn positioning — documented.
    assert "'unsafe-inline'" in _csp_directive(csp, "style-src")
    assert "frame-ancestors 'none'" in csp
    assert h["X-Frame-Options"] == "DENY"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["Cache-Control"] == "no-store"


def test_origin_check() -> None:
    allowed = {"127.0.0.1:8765"}
    assert origin_ok(origin="http://127.0.0.1:8765/whatever", allowed_hosts=allowed) is True
    assert origin_ok(origin="https://evil.com", allowed_hosts=allowed) is False
    assert origin_ok(origin=None, allowed_hosts=allowed) is False
    assert origin_ok(origin="garbage", allowed_hosts=allowed) is False


def test_csrf_double_submit_requires_match() -> None:
    assert csrf_ok(cookie_token="abc", header_token="abc") is True
    assert csrf_ok(cookie_token="abc", header_token="def") is False
    assert csrf_ok(cookie_token=None, header_token="abc") is False
    assert csrf_ok(cookie_token="abc", header_token=None) is False


def test_rate_limiter_blocks_after_max() -> None:
    rl = RateLimiter(max_events=3, window_seconds=60.0)
    assert all(rl.allow("o", now=t) for t in (1, 2, 3))
    assert rl.allow("o", now=4) is False  # 4th hit in window blocked
    # Sliding window: after the oldest expires, new ones are allowed again.
    assert rl.allow("o", now=70) is True


# ── app-level integration ────────────────────────────────────────────────────
def _client(tmp_path: Path) -> tuple[TestClient, ApprovalQueue, LoginToken]:
    queue = ApprovalQueue(tmp_path / "apv.db")
    sessions = Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key()))
    token = LoginToken()
    deps = DashboardDeps(
        queue=queue,
        sessions=sessions,
        login_token=token,
        allowed_hosts={"testserver"},
    )
    app = create_app(deps)
    return TestClient(app, base_url="http://testserver"), queue, token


def test_loopback_only_bind() -> None:
    queue = ApprovalQueue("/tmp/_apv_test_only.db") if False else None  # type-only stub
    deps = DashboardDeps(
        queue=ApprovalQueue(":memory:") if False else queue,  # not used
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=LoginToken(),
        allowed_hosts={"x"},
    )
    # The factory MUST refuse a non-loopback bind even if asked.
    with pytest.raises(ValueError, match="loopback"):
        create_app(deps, bind_host="0.0.0.0")  # noqa: S104  - testing this is refused


def test_home_requires_session(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 401


def test_security_headers_on_response(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    r = client.get("/login")
    assert r.status_code == 200
    assert r.headers["X-Frame-Options"] == "DENY"
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    # Scripts stay strict — no inline, only own bundles + nonce.
    assert "'unsafe-inline'" not in _csp_directive(csp, "script-src")
    assert "'nonce-" in _csp_directive(csp, "script-src")
    # Styles allow inline (Radix popover positioning) — narrow, documented concession.
    assert "'unsafe-inline'" in _csp_directive(csp, "style-src")


def _csp_directive(csp: str, name: str) -> str:
    for chunk in csp.split(";"):
        chunk = chunk.strip()
        if chunk.startswith(name + " "):
            return chunk
    return ""


def test_login_with_wrong_token_rejected(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)
    r = client.post(
        "/login",
        data={"token": "not-the-real-thing"},
        headers={"origin": "http://testserver", "x-midas-csrf": "x"},
        cookies={"midas_csrf": "x"},
    )
    assert r.status_code == 401


def test_login_succeeds_then_token_is_burned(tmp_path: Path) -> None:
    client, _, token = _client(tmp_path)
    value = token.value
    r = client.post(
        "/login",
        data={"token": value},
        headers={"origin": "http://testserver", "x-midas-csrf": "x"},
        cookies={"midas_csrf": "x"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert SESSION_COOKIE in r.cookies
    assert CSRF_COOKIE in r.cookies

    # Token now consumed: re-using it must fail.
    r2 = client.post(
        "/login",
        data={"token": value},
        headers={"origin": "http://testserver", "x-midas-csrf": "x"},
        cookies={"midas_csrf": "x"},
    )
    assert r2.status_code == 401


def test_state_changing_request_without_csrf_blocked(tmp_path: Path) -> None:
    client, queue, token = _client(tmp_path)
    queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    _sign_in(client, token)

    # No CSRF header → 403, the queue does NOT advance.
    r = client.post(
        "/approvals/1/approve",
        headers={"origin": "http://testserver"},  # CSRF header missing
    )
    assert r.status_code == 403
    from midas.core.approvals import ApprovalStatus
    assert queue.get(1).status == ApprovalStatus.PENDING


def test_state_changing_with_bad_origin_blocked(tmp_path: Path) -> None:
    client, queue, token = _client(tmp_path)
    queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    csrf = _sign_in(client, token)

    r = client.post(
        "/approvals/1/approve",
        headers={"origin": "https://evil.com", "x-midas-csrf": csrf},
    )
    assert r.status_code == 403


def test_approve_via_dashboard_uses_same_queue(tmp_path: Path) -> None:
    client, queue, token = _client(tmp_path)
    req = queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    csrf = _sign_in(client, token)

    r = client.post(
        f"/approvals/{req.id}/approve",
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
    )
    assert r.status_code == 200
    from midas.core.approvals import ApprovalStatus
    assert queue.get(req.id).status == ApprovalStatus.APPROVED


def test_idempotency_returns_409(tmp_path: Path) -> None:
    client, queue, token = _client(tmp_path)
    req = queue.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    csrf = _sign_in(client, token)
    headers = {"origin": "http://testserver", "x-midas-csrf": csrf}
    assert client.post(f"/approvals/{req.id}/approve", headers=headers).status_code == 200
    assert client.post(f"/approvals/{req.id}/approve", headers=headers).status_code == 409


def test_no_openapi_docs_exposed(tmp_path: Path) -> None:
    # Production hardening: no docs UI, no schema endpoint to fingerprint.
    client, _, _ = _client(tmp_path)
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = client.get(path)
        assert r.status_code == 404, path


# ── helper ────────────────────────────────────────────────────────────────────
def _sign_in(client: TestClient, token: LoginToken) -> str:
    """Complete the login dance. Returns the CSRF token to use in subsequent POSTs."""
    value = token.value
    r = client.post(
        "/login",
        data={"token": value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return r.cookies[CSRF_COOKIE]
