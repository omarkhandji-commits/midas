"""Dashboard auth primitives: constant-time compare, signed cookies, one-time token.

These are pure-logic tests — no FastAPI, no network. The HTTP-level defenses are
tested separately in test_dashboard_security.py.
"""

from __future__ import annotations

import pytest

from midas.flagship.dashboard.auth import (
    LoginToken,
    SessionConfig,
    Sessions,
    generate_secret_key,
)


def _sessions(owner: str = "owner") -> Sessions:
    return Sessions(SessionConfig(owner_id=owner, secret_key=generate_secret_key()))


# ── sessions ─────────────────────────────────────────────────────────────────
def test_secret_key_minimum_length() -> None:
    with pytest.raises(ValueError, match="32"):
        Sessions(SessionConfig(owner_id="o", secret_key=b"too short"))


def test_round_trip_succeeds() -> None:
    s = _sessions()
    assert s.verify(s.issue()) is True


def test_tampered_cookie_rejected() -> None:
    s = _sessions()
    cookie = s.issue()
    owner, expiry, mac = cookie.split("|")
    forged = f"{owner}|{expiry}|{'0' * len(mac)}"  # wrong MAC
    assert s.verify(forged) is False


def test_expired_cookie_rejected() -> None:
    s = _sessions()
    # Issue at t=0, verify well past TTL.
    cookie = s.issue(now=0)
    assert s.verify(cookie, now=10_000_000) is False


def test_different_key_rejects_cookie() -> None:
    # A cookie signed by another instance must not validate here. Defends against
    # stolen-cookie replay against a freshly restarted dashboard with a new key.
    s1 = _sessions("owner")
    s2 = _sessions("owner")  # different secret_key
    assert s2.verify(s1.issue()) is False


def test_wrong_owner_rejected() -> None:
    s1 = _sessions("alice")
    s2 = Sessions(SessionConfig(owner_id="bob", secret_key=s1._cfg.secret_key))  # type: ignore[attr-defined]
    assert s2.verify(s1.issue()) is False


def test_garbage_cookie_rejected() -> None:
    s = _sessions()
    for junk in ("", "x", "a|b", "a|b|c|d", "owner|notanint|" + "0" * 64):
        assert s.verify(junk) is False, junk


# ── one-time login token ─────────────────────────────────────────────────────
def test_login_token_is_single_use() -> None:
    tok = LoginToken()
    value = tok.value  # captured BEFORE consume; the property zeroes on success
    assert tok.consume(value) is True
    # A second use must fail even with the exact same string. No replay.
    assert tok.consume(value) is False


def test_login_token_wrong_value_rejected() -> None:
    tok = LoginToken()
    assert tok.consume("not-the-token") is False
    # And the genuine token still works afterwards (wrong attempts don't burn it).
    assert tok.consume(tok.value) is True


def test_login_token_is_long_enough() -> None:
    # 32 random bytes → at least 32 chars of urlsafe-b64. Brute-force-resistant.
    assert len(LoginToken().value) >= 32
