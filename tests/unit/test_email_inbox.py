"""email.inbox.read — credential gate, port refusal, parsing.

The IMAP socket path is not exercised in unit tests; we test the policy
and parsing logic that wraps it.
"""

from __future__ import annotations

import email

import pytest

from midas.flagship.agent.tools.email_inbox import (
    InboxError,
    _body_snippet,
    _decode,
    _from_parts,
    _has_attachment,
    _parse_date_iso,
    read_inbox,
)


def test_decode_handles_rfc2047_utf8() -> None:
    raw = "=?utf-8?b?SGVsbG8sIFdvcmxk?="  # base64("Hello, World")
    assert _decode(raw) == "Hello, World"


def test_decode_returns_empty_on_none() -> None:
    assert _decode(None) == ""
    assert _decode("") == ""


def test_from_parts_splits_display_name_and_address() -> None:
    name, addr = _from_parts('"Jane Smith" <jane@example.com>')
    assert name == "Jane Smith"
    assert addr == "jane@example.com"


def test_from_parts_lowercases_address() -> None:
    _, addr = _from_parts("Loud <BUYER@EXAMPLE.COM>")
    assert addr == "buyer@example.com"


def test_body_snippet_plain_text() -> None:
    msg = email.message_from_string(
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Hi! I'd love a quote for my bakery website."
    )
    snippet = _body_snippet(msg)
    assert "bakery website" in snippet


def test_body_snippet_caps_length() -> None:
    body = "x" * 2_000
    msg = email.message_from_string(
        f"Content-Type: text/plain; charset=utf-8\n\n{body}"
    )
    assert len(_body_snippet(msg, limit=500)) == 500


def test_has_attachment_true() -> None:
    raw = (
        "MIME-Version: 1.0\n"
        'Content-Type: multipart/mixed; boundary="b"\n\n'
        "--b\n"
        "Content-Type: text/plain\n\n"
        "see attached\n"
        "--b\n"
        'Content-Type: application/pdf; name="quote.pdf"\n'
        "Content-Disposition: attachment; filename=quote.pdf\n\n"
        "(binary)\n"
        "--b--\n"
    )
    msg = email.message_from_string(raw)
    assert _has_attachment(msg) is True


def test_has_attachment_false_on_plain_text() -> None:
    msg = email.message_from_string(
        "Content-Type: text/plain\n\nno attachment here"
    )
    assert _has_attachment(msg) is False


def test_parse_date_iso_handles_rfc822() -> None:
    iso = _parse_date_iso("Mon, 1 Sep 2025 14:30:00 +0000")
    assert iso.startswith("2025-09-01T14:30:00")


def test_parse_date_iso_handles_garbage() -> None:
    assert _parse_date_iso("not a date") == ""
    assert _parse_date_iso(None) == ""


def test_read_inbox_refuses_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.delenv("IMAP_USER", raising=False)
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)
    with pytest.raises(InboxError, match="IMAP_HOST"):
        read_inbox()


def test_read_inbox_refuses_plaintext_port_143(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USER", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_PORT", "143")
    with pytest.raises(InboxError, match="plaintext IMAP"):
        read_inbox()


def test_read_inbox_refuses_bad_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USER", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_PORT", "not-a-number")
    with pytest.raises(InboxError, match="must be an integer"):
        read_inbox()


def test_read_inbox_refuses_oversized_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USER", "me@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    with pytest.raises(InboxError, match="limit must be"):
        read_inbox(limit=500)
