"""Dashboard auth — owner-only, no passwords, no third parties.

Threat model: this is a LOCAL dashboard bound to 127.0.0.1. Even so, we assume:
- malicious processes on the box may try to read cookies via DevTools / extensions;
- other apps may try to forge CSRF requests from a browser tab;
- a stolen token must not let an attacker mint long-lived sessions silently.

Defenses:
- one-time login token printed to the OPERATOR'S TERMINAL on startup. No password
  storage, no email, no recovery flow — pure capability hand-off;
- HMAC-SHA256-signed session cookie (`owner|expiry|hex_mac`); rejected if expired,
  signed with a different key, or tampered;
- `hmac.compare_digest` everywhere we compare a secret — no timing side channel;
- session lifetime is short by default (1h), refreshed only on owner activity;
- the in-memory login token is single-use, cleared after first successful exchange.

This module is pure logic — no FastAPI imports. It's tested without a server.
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

_SESSION_TTL_SECONDS = 3600  # 1 hour; the dashboard refreshes on activity.


def _hmac_hex(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), sha256).hexdigest()


def _secure_eq(a: str, b: str) -> bool:
    """Constant-time string compare. Never short-circuit on a secret."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass
class SessionConfig:
    owner_id: str  # the operator id this session represents
    secret_key: bytes  # 32+ bytes of entropy. Generated once at runtime if absent.
    ttl_seconds: int = _SESSION_TTL_SECONDS


class Sessions:
    """Issues + verifies signed session cookies. No server-side session store needed."""

    def __init__(self, config: SessionConfig) -> None:
        if len(config.secret_key) < 32:
            raise ValueError("secret_key must be at least 32 bytes")
        self._cfg = config

    def issue(self, *, now: float | None = None) -> str:
        ts = int(now if now is not None else time.time())
        expiry = ts + self._cfg.ttl_seconds
        body = f"{self._cfg.owner_id}|{expiry}"
        return f"{body}|{_hmac_hex(self._cfg.secret_key, body)}"

    def verify(self, cookie: str | None, *, now: float | None = None) -> bool:
        if not cookie:
            return False
        parts = cookie.split("|")
        if len(parts) != 3:
            return False
        owner, expiry_s, mac = parts
        if not _secure_eq(owner, self._cfg.owner_id):
            return False
        try:
            expiry = int(expiry_s)
        except ValueError:
            return False
        ts = int(now if now is not None else time.time())
        if expiry < ts:
            return False
        expected = _hmac_hex(self._cfg.secret_key, f"{owner}|{expiry_s}")
        return _secure_eq(expected, mac)


class LoginToken:
    """One-time, single-use terminal-printed token to exchange for a session cookie."""

    def __init__(self, value: str | None = None) -> None:
        # 32 random bytes → 43-char URL-safe string. Long enough to brute-force-resist.
        self._value: str | None = value or secrets.token_urlsafe(32)
        self._used = False

    @property
    def value(self) -> str:
        assert self._value is not None
        return self._value

    def consume(self, candidate: str) -> bool:
        """Returns True exactly once, for the right token. Wrong/used → False."""
        if self._value is None or self._used:
            return False
        if not _secure_eq(candidate, self._value):
            return False
        self._used = True
        self._value = None  # zero out so a subsequent log dump can't reveal it
        return True


def generate_secret_key() -> bytes:
    """A fresh 64-byte key. Persisted to disk by the runtime, never logged."""
    return secrets.token_bytes(64)
