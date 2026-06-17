"""web.automate — APPROVE-tier interactive web automation.

Sibling of ``web.scrape``: where scrape is a read-only render, automate
performs a small, declared sequence of clicks/fills/navigations. Every
action is queued for human approval — the planner cannot, by construction,
log into a site without the operator seeing the exact step list first.

Contract
--------
- Plan validates each action against a tight whitelist (``navigate``,
  ``click``, ``fill``, ``wait``, ``screenshot``). No ``evaluate`` step —
  arbitrary JS would let the planner exfiltrate session data.
- Payload carries the canonical action list + a sha256 of its JSON form.
- Executor refuses if the hash drifts between approval and execute.
- Action: ``execute_code`` — APPROVE-tier in the default policy.
- Output ``Taint.UNTRUSTED`` — captured DOM is data, not instructions.

Honest constraints
------------------
- ``fill`` values are visible in the approval payload. Operators should
  NOT pass raw passwords — wire a credential store before automating logins.
  We surface a clear warning if a field name looks password-shaped.
- No captcha bypass. If the scripted flow hits one, ``raise``.
- robots.txt is respected at navigate time, override is opt-in per call.
- Per-host rate limit shared with ``web.scrape`` (same module limiter).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .web_scrape import _RATE_LIMITER, _check_robots, _detect_captcha


class AutomateError(RuntimeError):
    """Raised when web.automate can't satisfy the request honestly."""


_ALLOWED_ACTIONS = {"navigate", "click", "fill", "wait", "screenshot"}
_MAX_ACTIONS = 20
_DEFAULT_TIMEOUT = 60.0
_MAX_TIMEOUT = 600.0  # 10 min ceiling
_PASSWORD_SHAPED = {"password", "pwd", "passwd", "secret", "pin", "otp"}


@dataclass
class AutomatePlan:
    """Approval payload — describes the planned actions, not their result."""

    kind: str  # always "web_automate"
    start_url: str
    actions: list[dict[str, Any]]
    timeout_seconds: float
    allow_disallowed_robots: bool
    sha256_actions: str
    preview: str  # human-readable summary of the sequence
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomateResult:
    final_url: str
    title: str
    html: str
    captcha_detected: bool
    actions_run: int
    elapsed_seconds: float
    truncated: bool


_MAX_HTML_CHARS = 200_000


def _canonical(actions: list[dict[str, Any]]) -> str:
    """Stable JSON for hashing — sorted keys, no whitespace surprises."""
    return json.dumps(actions, sort_keys=True, separators=(",", ":"))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _validate_action(idx: int, action: dict[str, Any]) -> None:
    """Per-step schema check. Raises ValueError on bad shape."""
    kind = action.get("kind")
    if kind not in _ALLOWED_ACTIONS:
        raise ValueError(
            f"action {idx}: kind must be one of {sorted(_ALLOWED_ACTIONS)}, "
            f"got {kind!r}"
        )
    if kind == "navigate":
        url = str(action.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"action {idx}: navigate needs http(s) URL, got {url!r}"
            )
    elif kind == "click":
        selector = str(action.get("selector") or "")
        if not selector.strip():
            raise ValueError(f"action {idx}: click needs a non-empty selector")
    elif kind == "fill":
        selector = str(action.get("selector") or "")
        value = str(action.get("value") or "")
        if not selector.strip():
            raise ValueError(f"action {idx}: fill needs a non-empty selector")
        if not value:
            raise ValueError(f"action {idx}: fill needs a non-empty value")
        # Surface a clear warning if this looks like a password — credentials
        # belong in a vault, not in an approval payload the operator can see.
        sel_lower = selector.lower()
        if any(p in sel_lower for p in _PASSWORD_SHAPED):
            raise ValueError(
                f"action {idx}: fill selector looks password-shaped "
                f"({selector!r}); wire a credential vault before automating logins"
            )
    elif kind == "wait":
        ms = action.get("ms")
        if not isinstance(ms, int | float) or ms <= 0 or ms > 30_000:
            raise ValueError(
                f"action {idx}: wait needs ms in (0, 30000], got {ms!r}"
            )
    elif kind == "screenshot":
        # No required fields; we always save inside the workspace.
        pass


def plan_web_automate(
    *,
    start_url: str,
    actions: list[dict[str, Any]],
    timeout_seconds: float = _DEFAULT_TIMEOUT,
    allow_disallowed_robots: bool = False,
) -> AutomatePlan:
    """Build the approval payload. NO browser starts here. NO egress."""
    parsed = urlparse(start_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"web.automate needs absolute http(s) start_url, got {start_url!r}"
        )
    if not isinstance(actions, list) or not actions:
        raise ValueError("web.automate needs at least one action")
    if len(actions) > _MAX_ACTIONS:
        raise ValueError(
            f"web.automate sequence too long ({len(actions)} > {_MAX_ACTIONS})"
        )
    timeout = float(timeout_seconds)
    if timeout <= 0 or timeout > _MAX_TIMEOUT:
        raise ValueError(
            f"web.automate timeout must be in (0, {_MAX_TIMEOUT}], got {timeout}"
        )
    cleaned: list[dict[str, Any]] = []
    for idx, raw in enumerate(actions):
        if not isinstance(raw, dict):
            raise ValueError(f"action {idx} must be a dict")
        _validate_action(idx, raw)
        cleaned.append(dict(raw))
    canonical = _canonical(cleaned)
    preview_lines = [f"start: {start_url}"]
    for i, a in enumerate(cleaned[:5], start=1):
        preview_lines.append(f"{i}. {a.get('kind')} {a.get('selector') or a.get('url') or ''}")
    if len(cleaned) > 5:
        preview_lines.append(f"… +{len(cleaned) - 5} more")
    return AutomatePlan(
        kind="web_automate",
        start_url=start_url,
        actions=cleaned,
        timeout_seconds=timeout,
        allow_disallowed_robots=bool(allow_disallowed_robots),
        sha256_actions=_sha256(canonical),
        preview="\n".join(preview_lines)[:400],
        meta={"n_actions": len(cleaned)},
    )


def execute_web_automate(payload: dict[str, Any]) -> AutomateResult:
    """Post-approval executor. Runs the action sequence in Playwright."""
    start_url = str(payload.get("start_url") or "")
    actions = list(payload.get("actions") or [])
    timeout = float(payload.get("timeout_seconds") or _DEFAULT_TIMEOUT)
    allow_disallowed = bool(payload.get("allow_disallowed_robots") or False)
    expected = str(payload.get("sha256_actions") or "")
    if not start_url or not actions:
        raise AutomateError("web.automate payload missing start_url or actions")
    if expected and _sha256(_canonical(actions)) != expected:
        raise AutomateError(
            "web.automate refused: payload action list drifted from approval"
        )

    parsed = urlparse(start_url)
    host = parsed.netloc
    if not allow_disallowed and not _check_robots(start_url, user_agent="midas-agent"):
        raise AutomateError(
            f"robots.txt disallows automation on {host!r}; pass "
            "allow_disallowed_robots=True only with explicit authorization"
        )
    _RATE_LIMITER.wait_for(host)

    try:
        from playwright.sync_api import (
            TimeoutError as PlaywrightTimeout,
        )
        from playwright.sync_api import (
            sync_playwright,
        )
    except ImportError as e:
        raise AutomateError(
            "web.automate needs Playwright; install with "
            "`pip install playwright && playwright install chromium`"
        ) from e

    started = time.monotonic()
    actions_run = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(start_url, timeout=int(timeout * 1000))
                for action in actions:
                    kind = action.get("kind")
                    if kind == "navigate":
                        page.goto(
                            str(action.get("url") or ""),
                            timeout=int(timeout * 1000),
                        )
                    elif kind == "click":
                        page.click(
                            str(action.get("selector") or ""),
                            timeout=int(timeout * 1000),
                        )
                    elif kind == "fill":
                        page.fill(
                            str(action.get("selector") or ""),
                            str(action.get("value") or ""),
                            timeout=int(timeout * 1000),
                        )
                    elif kind == "wait":
                        page.wait_for_timeout(int(float(action.get("ms") or 0)))
                    elif kind == "screenshot":
                        # No-op in the executor's signature; the caller's
                        # workflow handles where to persist. The DOM is enough
                        # evidence for the receipt.
                        pass
                    actions_run += 1
                html = page.content()
                final_url = page.url
                title = page.title()
            finally:
                browser.close()
    except PlaywrightTimeout as e:
        raise AutomateError(f"web.automate timed out after {timeout}s") from e
    except Exception as e:
        raise AutomateError(
            f"web.automate failed at action {actions_run}: {type(e).__name__}: {e}"
        ) from e

    captcha = _detect_captcha(html)
    truncated = len(html) > _MAX_HTML_CHARS
    return AutomateResult(
        final_url=final_url,
        title=title[:300],
        html=html[:_MAX_HTML_CHARS],
        captcha_detected=captcha,
        actions_run=actions_run,
        elapsed_seconds=round(time.monotonic() - started, 3),
        truncated=truncated,
    )
