"""newsletter.draft — CAN-SPAM / CASL footer enforcement."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.newsletter import (
    NewsletterError,
    plan_newsletter,
)

_ADDR = "123 Main St, Montreal, QC H1A 1A1, Canada"
_UNSUB = "https://kenzassweet.ca/unsubscribe?token=abc"


def test_basic_render_contains_required_legal_bits():
    d = plan_newsletter(
        subject="June newsletter",
        body="# Hello\n\nThis is the body.",
        unsubscribe_url=_UNSUB,
        physical_address=_ADDR,
    )
    assert _UNSUB in d.html
    assert _UNSUB in d.plaintext
    assert _ADDR in d.html
    assert _ADDR in d.plaintext
    assert d.sha256_intent


def test_refuses_missing_unsubscribe():
    with pytest.raises(NewsletterError, match="unsubscribe URL"):
        plan_newsletter(
            subject="Hi", body="body",
            unsubscribe_url="", physical_address=_ADDR,
        )


def test_refuses_non_https_unsubscribe():
    with pytest.raises(NewsletterError, match="unsubscribe URL"):
        plan_newsletter(
            subject="Hi", body="body",
            unsubscribe_url="ftp://nope", physical_address=_ADDR,
        )


def test_refuses_missing_address():
    with pytest.raises(NewsletterError, match="physical postal address"):
        plan_newsletter(
            subject="Hi", body="body",
            unsubscribe_url=_UNSUB, physical_address="",
        )


def test_refuses_empty_subject():
    with pytest.raises(NewsletterError, match="non-empty subject"):
        plan_newsletter(
            subject="   ", body="body",
            unsubscribe_url=_UNSUB, physical_address=_ADDR,
        )


def test_refuses_empty_body():
    with pytest.raises(NewsletterError, match="non-empty body"):
        plan_newsletter(
            subject="Hi", body="",
            unsubscribe_url=_UNSUB, physical_address=_ADDR,
        )


def test_md_converts_headings_and_bold():
    d = plan_newsletter(
        subject="x",
        body="# H1\n\nText with **bold** word.",
        unsubscribe_url=_UNSUB,
        physical_address=_ADDR,
    )
    assert "<h1>H1</h1>" in d.html
    assert "<strong>bold</strong>" in d.html


def test_links_escape_non_http_destinations():
    d = plan_newsletter(
        subject="x",
        body="[ok](https://example.com) [bad](javascript:alert(1))",
        unsubscribe_url=_UNSUB,
        physical_address=_ADDR,
    )
    assert 'href="https://example.com"' in d.html
    # No clickable javascript: URL — escaped text in a hidden preview div is
    # inert (html.escape neutralizes it), but no href anchor should carry it.
    assert 'href="javascript:' not in d.html.lower()
    assert 'href="data:' not in d.html.lower()


def test_preview_text_capped_at_90_chars():
    d = plan_newsletter(
        subject="x",
        body="ok",
        preview_text="A" * 200,
        unsubscribe_url=_UNSUB,
        physical_address=_ADDR,
    )
    assert len(d.preview_text) == 90


def test_html_escapes_subject():
    d = plan_newsletter(
        subject="<script>alert(1)</script>",
        body="ok",
        unsubscribe_url=_UNSUB,
        physical_address=_ADDR,
    )
    assert "<script>" not in d.html
    assert "&lt;script&gt;" in d.html


def test_intent_hash_changes_with_body():
    a = plan_newsletter(
        subject="x", body="A",
        unsubscribe_url=_UNSUB, physical_address=_ADDR,
    )
    b = plan_newsletter(
        subject="x", body="B",
        unsubscribe_url=_UNSUB, physical_address=_ADDR,
    )
    assert a.sha256_intent != b.sha256_intent
