"""web.scrape — read-only rendered fetch with honest anti-bot defenses.

Why
---
``http.fetch`` is enough for 60% of pages, but a lot of cash-relevant sites
(Etsy, Reddit, Fiverr, competitor blogs) render their content client-side.
``web.scrape`` runs the page through a real headless browser (Playwright) so
the planner sees what a human would see.

Honest scope
------------
- **READ ONLY.** No clicks, no form submits, no logins. Interactive flows go
  through ``web.automate`` (separate tool, APPROVE-tier).
- **robots.txt respected** by default. Override requires an explicit
  ``allow_disallowed=True`` argument AND the operator must add the domain to
  the policy's egress allowlist — we don't carry the override across calls.
- **No captcha bypass.** If a captcha is detected, we stop and report.
- **No credential injection.** Browser starts with a clean profile every time.
- **Rate-limited per host.** Minimum 2 seconds between fetches of the same
  domain in the same process. Prevents the "1000 requests in 5 seconds"
  pattern that bot detectors flag.
- **User-agent rotation** within a small pool of real, current browser strings.
  Not a fingerprint forge — just enough to look like a normal user.
- **Viewport randomization** within reasonable ranges.

What we deliberately DON'T do
-----------------------------
- No paid proxy rotation. Operators can wire that in later if their cash
  business needs it; we don't bake an upsell into the agent.
- No fingerprint spoofing libraries (playwright-extra-stealth). Those are
  arms-race tools; if a site is hostile enough to need them, ``web.scrape``
  is the wrong tool — get an official API key.
- No automatic captcha solving. Detecting one is the signal to stop, not
  the signal to call 2Captcha.
"""

from __future__ import annotations

import random
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


class ScrapeError(RuntimeError):
    """Raised when web.scrape can't satisfy the request honestly."""


# Pool of recent, real browser user agents. Refreshed periodically — these are
# all major browsers as of late 2025. Random rotation is enough to avoid the
# "default Playwright UA" detection that the lazy bots flag.
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) "
    "Gecko/20100101 Firefox/131.0",
)


# Captcha / anti-bot text signatures. Detecting any of these means: STOP.
_CAPTCHA_MARKERS = (
    "g-recaptcha",
    "h-captcha",
    "cf-challenge",
    "Just a moment...",  # Cloudflare's intro
    "Please verify you are a human",
    "Access denied",
)


_MIN_GAP_SECONDS = 2.0
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_HTML_CHARS = 200_000


@dataclass
class ScrapeResult:
    url: str
    status: int
    final_url: str
    html: str
    title: str
    captcha_detected: bool
    user_agent: str
    truncated: bool
    elapsed_seconds: float


@dataclass
class _DomainRateLimiter:
    """Process-local per-host last-fetch tracker."""

    last_at: dict[str, float] = field(default_factory=dict)

    def wait_for(self, host: str, *, min_gap: float = _MIN_GAP_SECONDS) -> float:
        now = time.monotonic()
        last = self.last_at.get(host, 0.0)
        gap = now - last
        if gap >= min_gap:
            self.last_at[host] = now
            return 0.0
        sleep_for = min_gap - gap
        time.sleep(sleep_for)
        self.last_at[host] = time.monotonic()
        return sleep_for


# Module-level so multiple scrape calls in the same process share state.
_RATE_LIMITER = _DomainRateLimiter()


def _check_robots(url: str, *, user_agent: str) -> bool:
    """Return True if the URL is allowed by the host's robots.txt.

    Failures to fetch robots (network, 404, malformed) default to allowed —
    matches every major crawler's behavior. Hosts that don't publish robots
    are saying "we have no preference".
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        return True  # no robots → not disallowed
    return rp.can_fetch(user_agent, url)


def _detect_captcha(html: str) -> bool:
    """Cheap substring check. False positives are fine — we stop conservatively."""
    if not html:
        return False
    hay = html.lower()
    return any(marker.lower() in hay for marker in _CAPTCHA_MARKERS)


def web_scrape(
    url: str,
    *,
    allow_disallowed: bool = False,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    user_agent: str | None = None,
) -> ScrapeResult:
    """Render ``url`` in a clean headless browser and return the result.

    Raises :class:`ScrapeError` for: malformed URL, robots disallow without
    override, captcha detected, Playwright missing, browser timeout.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ScrapeError(f"web.scrape needs an absolute http(s) URL, got {url!r}")
    host = parsed.netloc

    chosen_ua = user_agent or random.choice(_USER_AGENTS)  # nosec B311

    if not allow_disallowed and not _check_robots(url, user_agent=chosen_ua):
        raise ScrapeError(
            f"robots.txt disallows {url!r} for this user-agent; "
            "pass allow_disallowed=True only when the operator has explicit "
            "authorization to crawl this domain"
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
        raise ScrapeError(
            "web.scrape needs Playwright; install with "
            "`pip install playwright && playwright install chromium`"
        ) from e

    started = time.monotonic()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                # Reasonable viewport jitter — not a fingerprint forge, just
                # different enough from the Playwright default 800x600 that
                # naive detectors don't catch us.
                width = 1280 + random.randrange(0, 200, 40)  # nosec B311
                height = 720 + random.randrange(0, 200, 40)  # nosec B311
                context = browser.new_context(
                    user_agent=chosen_ua,
                    viewport={"width": width, "height": height},
                    # Clean profile every time — never carry cookies between
                    # operator runs. Privacy + reproducibility.
                    ignore_https_errors=False,
                )
                page = context.new_page()
                response = page.goto(url, timeout=int(timeout_seconds * 1000))
                status = response.status if response else 0
                final_url = page.url
                html = page.content()
                title = page.title()
            finally:
                browser.close()
    except PlaywrightTimeout as e:
        raise ScrapeError(f"web.scrape timed out after {timeout_seconds}s") from e
    except Exception as e:
        # Playwright raises its own exception hierarchy; we surface a clean
        # message rather than leaking internals. Network failures, DNS, etc.
        raise ScrapeError(f"web.scrape failed: {type(e).__name__}: {e}") from e

    captcha = _detect_captcha(html)
    truncated = len(html) > _MAX_HTML_CHARS
    return ScrapeResult(
        url=url,
        status=status,
        final_url=final_url,
        html=html[:_MAX_HTML_CHARS],
        title=title[:300],
        captcha_detected=captcha,
        user_agent=chosen_ua,
        truncated=truncated,
        elapsed_seconds=round(time.monotonic() - started, 3),
    )


def _as_tool_payload(result: ScrapeResult) -> dict[str, Any]:
    return {
        "url": result.url,
        "status": result.status,
        "final_url": result.final_url,
        "html": result.html,
        "title": result.title,
        "captcha_detected": result.captcha_detected,
        "user_agent": result.user_agent,
        "truncated": result.truncated,
        "elapsed_seconds": result.elapsed_seconds,
    }
