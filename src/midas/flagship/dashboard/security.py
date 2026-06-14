"""HTTP-level defenses applied to every dashboard response and request.

What this module covers:
- strict response headers: CSP (no inline scripts via nonce, no remote sources), HSTS,
  X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy no-referrer,
  Cross-Origin-Opener-Policy same-origin, Permissions-Policy minimal;
- CSRF defense for state-changing requests: double-submit cookie + a strict Origin
  check (request must originate from the same host the dashboard is bound to);
- a tiny in-memory rate limiter per owner (linear cost per call, bounded memory).

The CSP intentionally forbids `unsafe-inline`. The dashboard ships its own CSS/JS
under /static — no CDN, no Tailwind dump, no telemetry.
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _secure_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ── headers ──────────────────────────────────────────────────────────────────
def security_headers(*, nonce: str) -> dict[str, str]:
    """The set of response headers applied to every response.

    `nonce` is per-response and consumed by inline-script policy if used (we don't
    use inline scripts; the nonce just hardens CSP against accidental injection).
    """
    # Script-src is locked: nothing inline, only own hashed bundles + the nonce-tagged
    # legacy bootstrap. Style-src concedes `'unsafe-inline'` because Radix/shadcn
    # primitives inject inline positioning styles at runtime (popovers, dialogs,
    # tooltips). Scope is narrow — styles only — and the dashboard is loopback-only
    # and owner-gated, so the residual XSS surface for inline styles is negligible.
    # Documented in docs/SECURITY.md and docs/THREAT_MODEL.md.
    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'; "
        "form-action 'self'"
    )
    return {
        "Content-Security-Policy": csp,
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",
    }


def make_nonce() -> str:
    return secrets.token_urlsafe(16)


# ── CSRF (double-submit + Origin check) ───────────────────────────────────────
def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(*, cookie_token: str | None, header_token: str | None) -> bool:
    """Defense: the attacker can't read the cookie (SameSite=Strict, HttpOnly=False
    for this token), so they can't put its value into a header. Both must match.
    """
    if not cookie_token or not header_token:
        return False
    return _secure_eq(cookie_token, header_token)


def origin_ok(*, origin: str | None, allowed_hosts: set[str]) -> bool:
    """The Origin header (or Referer fallback at the caller) must match one of the
    bound hosts. Requests with NO origin (curl, scripts) are blocked from POST."""
    if not origin:
        return False
    # Parse minimally to avoid pulling urllib; "<scheme>://<host>[:<port>][/...]" form.
    rest = origin.split("://", 1)
    if len(rest) != 2:
        return False
    host = rest[1].split("/", 1)[0]
    return host in allowed_hosts


def is_state_changing(method: str) -> bool:
    return method.upper() not in _SAFE_METHODS


# ── tiny per-owner rate limiter (no external deps) ────────────────────────────
@dataclass
class _Bucket:
    times: deque[float] = field(default_factory=deque)


class RateLimiter:
    """Sliding-window limiter, capped per identity.

    Memory is bounded: only the last `max_events` timestamps per identity are kept;
    older entries are popped on each call. Cleanup of stale identities happens lazily.
    """

    def __init__(self, *, max_events: int = 30, window_seconds: float = 60.0) -> None:
        self._max = max_events
        self._win = window_seconds
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, identity: str, *, now: float | None = None) -> bool:
        t = now if now is not None else time.time()
        bucket = self._buckets.setdefault(identity, _Bucket())
        cutoff = t - self._win
        while bucket.times and bucket.times[0] < cutoff:
            bucket.times.popleft()
        if len(bucket.times) >= self._max:
            return False
        bucket.times.append(t)
        return True
