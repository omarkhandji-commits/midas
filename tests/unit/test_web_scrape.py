"""web.scrape — robots.txt, captcha detection, rate limit, URL validation.

The Playwright launch path is NOT exercised in unit tests (it's a heavyweight
optional dep). We test the policy and parsing logic that runs around it —
that's where the honest behavior lives.
"""

from __future__ import annotations

import time

import pytest

from midas.flagship.agent.tools.web_scrape import (
    ScrapeError,
    _detect_captcha,
    _DomainRateLimiter,
    web_scrape,
)


def test_rejects_relative_url() -> None:
    with pytest.raises(ScrapeError, match="absolute http"):
        web_scrape("/not/a/url")


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ScrapeError, match="absolute http"):
        web_scrape("file:///etc/passwd")


def test_rejects_javascript_url() -> None:
    with pytest.raises(ScrapeError, match="absolute http"):
        web_scrape("javascript:alert(1)")


def test_detect_captcha_finds_recaptcha() -> None:
    html = '<div class="g-recaptcha" data-sitekey="x"></div>'
    assert _detect_captcha(html) is True


def test_detect_captcha_finds_cloudflare() -> None:
    assert _detect_captcha("<h1>Just a moment...</h1>") is True


def test_detect_captcha_clean_page() -> None:
    assert _detect_captcha("<h1>Welcome to our bakery</h1>") is False


def test_detect_captcha_handles_empty() -> None:
    assert _detect_captcha("") is False


def test_rate_limiter_enforces_minimum_gap() -> None:
    rl = _DomainRateLimiter()
    rl.wait_for("etsy.com", min_gap=0.05)
    started = time.monotonic()
    rl.wait_for("etsy.com", min_gap=0.05)
    elapsed = time.monotonic() - started
    assert elapsed >= 0.04, f"second fetch should have slept, got {elapsed}s"


def test_rate_limiter_independent_per_host() -> None:
    rl = _DomainRateLimiter()
    rl.wait_for("etsy.com", min_gap=0.5)
    started = time.monotonic()
    rl.wait_for("fiverr.com", min_gap=0.5)  # different host → no sleep
    elapsed = time.monotonic() - started
    assert elapsed < 0.2, f"different host should not sleep, got {elapsed}s"
