"""Dashboard — local, owner-only, Proof-First. Security defenses live next to the app."""

from .app import DashboardDeps, create_app
from .auth import LoginToken, SessionConfig, Sessions, generate_secret_key
from .security import (
    RateLimiter,
    csrf_ok,
    issue_csrf_token,
    make_nonce,
    origin_ok,
    security_headers,
)

__all__ = [
    "create_app",
    "DashboardDeps",
    "Sessions",
    "SessionConfig",
    "LoginToken",
    "generate_secret_key",
    "RateLimiter",
    "security_headers",
    "make_nonce",
    "csrf_ok",
    "origin_ok",
    "issue_csrf_token",
]
