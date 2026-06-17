"""email.send — recipient parsing, intent hash, unsubscribe, SMTP env."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.email_send import (
    SmtpSendError,
    _hash_intent,
    _looks_unsubscribable,
    _normalize_recipients,
    execute_email_send,
    plan_email_send,
)

# ── recipient parsing ─────────────────────────────────────────────────────


def test_normalize_handles_list_and_string() -> None:
    assert _normalize_recipients(["A@X.com", "  b@y.com  "]) == ["a@x.com", "b@y.com"]
    assert _normalize_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]


def test_normalize_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="not a valid email"):
        _normalize_recipients(["not-an-email"])


def test_normalize_empty_list_is_ok() -> None:
    assert _normalize_recipients([]) == []
    assert _normalize_recipients("") == []


# ── unsubscribe heuristic ─────────────────────────────────────────────────


def test_looks_unsubscribable_recognizes_phrases() -> None:
    assert _looks_unsubscribable("…click here to unsubscribe.")
    assert _looks_unsubscribable("Opt-out anytime.")
    assert _looks_unsubscribable("List-Unsubscribe: <mailto:u@x>")


def test_looks_unsubscribable_clean_email() -> None:
    assert not _looks_unsubscribable("Hi Sarah, I had a question about your post.")


# ── plan ──────────────────────────────────────────────────────────────────


def test_plan_basic_single_recipient() -> None:
    plan = plan_email_send(
        to="buyer@example.com",
        subject="About your bakery website",
        body="Hi Sarah, quick question about your last post…",
    )
    assert plan.to == ["buyer@example.com"]
    assert plan.sha256_intent == _hash_intent(
        to=plan.to, cc=[], bcc=[], subject=plan.subject, body=plan.body
    )


def test_plan_rejects_empty_subject() -> None:
    with pytest.raises(ValueError, match="non-empty subject"):
        plan_email_send(to="a@x.com", subject="   ", body="hi")


def test_plan_rejects_empty_body() -> None:
    with pytest.raises(ValueError, match="non-empty body"):
        plan_email_send(to="a@x.com", subject="hi", body="")


def test_plan_rejects_no_recipients() -> None:
    with pytest.raises(ValueError, match="at least one recipient"):
        plan_email_send(to=[], subject="hi", body="hi")


def test_plan_refuses_bulk_without_unsubscribe() -> None:
    with pytest.raises(ValueError, match="unsubscribe affordance"):
        plan_email_send(
            to=["a@x.com", "b@x.com"],
            subject="Launch news",
            body="We just shipped a new feature you'll love.",
        )


def test_plan_accepts_bulk_with_unsubscribe() -> None:
    plan = plan_email_send(
        to=["a@x.com", "b@x.com"],
        subject="Launch news",
        body="…you can unsubscribe at any time by replying STOP.",
    )
    assert plan.meta["n_recipients"] == 2


def test_plan_refuses_too_many_recipients() -> None:
    big = [f"u{i}@x.com" for i in range(101)]
    with pytest.raises(ValueError, match="too many recipients"):
        plan_email_send(
            to=big, subject="x", body="unsubscribe here"
        )


# ── execute env gates ─────────────────────────────────────────────────────


def test_execute_refuses_intent_drift() -> None:
    payload = {
        "to": ["a@x.com"],
        "cc": [],
        "bcc": [],
        "subject": "tampered subject",
        "body": "tampered body",
        "sha256_intent": _hash_intent(
            to=["a@x.com"], cc=[], bcc=[], subject="original", body="original",
        ),
    }
    with pytest.raises(SmtpSendError, match="intent hash drifted"):
        execute_email_send(payload)


def test_execute_refuses_missing_smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    payload = {
        "to": ["a@x.com"],
        "cc": [],
        "bcc": [],
        "subject": "hi",
        "body": "hi",
        "sha256_intent": _hash_intent(
            to=["a@x.com"], cc=[], bcc=[], subject="hi", body="hi"
        ),
    }
    with pytest.raises(SmtpSendError, match="SMTP_HOST"):
        execute_email_send(payload)


def test_execute_refuses_plaintext_port_25(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    monkeypatch.setenv("SMTP_PORT", "25")
    payload = {
        "to": ["a@x.com"],
        "cc": [],
        "bcc": [],
        "subject": "hi",
        "body": "hi",
        "sha256_intent": _hash_intent(
            to=["a@x.com"], cc=[], bcc=[], subject="hi", body="hi"
        ),
    }
    with pytest.raises(SmtpSendError, match="plaintext SMTP"):
        execute_email_send(payload)
