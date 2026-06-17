"""Stripe webhook verifier — HMAC, replay, idempotency, cash recording."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from midas.flagship.stripe_webhook import (
    StripeWebhookError,
    is_cash_event,
    parse_event,
    record_cash_from_event,
    verify_signature,
)

SECRET = "whsec_test_" + "a" * 32


def _sign(payload: bytes, ts: int) -> str:
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_verify_signature_accepts_valid_v1() -> None:
    payload = b'{"id":"evt_1"}'
    now = int(time.time())
    header = _sign(payload, now)
    verify_signature(
        payload=payload, signature_header=header, secret=SECRET, now=now
    )


def test_verify_signature_rejects_tampered_payload() -> None:
    now = int(time.time())
    header = _sign(b'{"id":"evt_original"}', now)
    with pytest.raises(StripeWebhookError, match="does not match"):
        verify_signature(
            payload=b'{"id":"evt_tampered"}',
            signature_header=header,
            secret=SECRET,
            now=now,
        )


def test_verify_signature_rejects_outside_tolerance() -> None:
    payload = b'{"id":"evt_1"}'
    ts = int(time.time()) - 1000  # 1000 seconds ago, default tolerance is 300
    header = _sign(payload, ts)
    with pytest.raises(StripeWebhookError, match="outside tolerance"):
        verify_signature(
            payload=payload, signature_header=header, secret=SECRET
        )


def test_verify_signature_rejects_malformed_header() -> None:
    with pytest.raises(StripeWebhookError, match="malformed"):
        verify_signature(
            payload=b"x", signature_header="garbage", secret=SECRET
        )


def test_verify_signature_rejects_missing_header() -> None:
    with pytest.raises(StripeWebhookError, match="missing"):
        verify_signature(payload=b"x", signature_header="", secret=SECRET)


def test_verify_signature_rejects_missing_secret() -> None:
    now = int(time.time())
    with pytest.raises(StripeWebhookError, match="not configured"):
        verify_signature(
            payload=b"x", signature_header=f"t={now},v1=abc", secret=""
        )


def test_verify_signature_accepts_atomic_secret_rotation() -> None:
    """When Stripe rotates a secret, a single header can carry multiple v1."""
    payload = b'{"id":"evt_1"}'
    now = int(time.time())
    valid = _sign(payload, now).split("v1=")[1]
    header = f"t={now},v1=deadbeef,v1={valid}"
    verify_signature(
        payload=payload, signature_header=header, secret=SECRET, now=now
    )


def test_parse_checkout_session_completed() -> None:
    body = json.dumps(
        {
            "id": "evt_abc",
            "type": "checkout.session.completed",
            "livemode": False,
            "data": {
                "object": {
                    "payment_link": "plink_xyz",
                    "payment_intent": "pi_123",
                    "amount_total": 4900,
                    "currency": "usd",
                    "customer_details": {"email": "buyer@example.com"},
                }
            },
        }
    ).encode()
    event = parse_event(body)
    assert event.id == "evt_abc"
    assert event.type == "checkout.session.completed"
    assert event.payment_link_id == "plink_xyz"
    assert event.amount_received == 4900
    assert event.currency == "usd"
    assert event.customer_email == "buyer@example.com"


def test_parse_payment_intent_succeeded() -> None:
    body = json.dumps(
        {
            "id": "evt_pi",
            "type": "payment_intent.succeeded",
            "livemode": True,
            "data": {
                "object": {
                    "id": "pi_999",
                    "amount_received": 12_300,
                    "currency": "eur",
                    "receipt_email": "client@example.com",
                    "metadata": {"payment_link": "plink_ml"},
                }
            },
        }
    ).encode()
    event = parse_event(body)
    assert event.id == "evt_pi"
    assert event.livemode is True
    assert event.payment_intent_id == "pi_999"
    assert event.amount_received == 12_300


def test_parse_rejects_garbage_json() -> None:
    with pytest.raises(StripeWebhookError, match="valid JSON"):
        parse_event(b"not json")


def test_parse_rejects_missing_id() -> None:
    body = json.dumps({"type": "payment_intent.succeeded"}).encode()
    with pytest.raises(StripeWebhookError, match="missing id or type"):
        parse_event(body)


def test_is_cash_event_filters_zero_amount() -> None:
    from midas.flagship.stripe_webhook import StripeEvent

    e = StripeEvent(
        id="x", type="checkout.session.completed", livemode=False,
        payment_link_id="", payment_intent_id="", amount_received=0,
        currency="usd", customer_email="",
    )
    assert not is_cash_event(e)


def test_is_cash_event_rejects_unrelated_types() -> None:
    from midas.flagship.stripe_webhook import StripeEvent

    e = StripeEvent(
        id="x", type="customer.created", livemode=False,
        payment_link_id="", payment_intent_id="", amount_received=100,
        currency="usd", customer_email="",
    )
    assert not is_cash_event(e)


class _FakeMemory:
    def __init__(self) -> None:
        self.cash_calls: list[dict] = []
        self.entries: list = []

    def recall(self, *, kind, limit=100):
        return list(self.entries)

    def record_cash(self, key, *, channel, offer, revenue_usd, cost_usd, sources):
        # Simulate the real MemoryStore — newest-first.
        class _Row:
            pass

        row = _Row()
        row.key = key
        self.entries.insert(0, row)
        self.cash_calls.append(
            {
                "key": key,
                "channel": channel,
                "offer": offer,
                "revenue_usd": revenue_usd,
                "cost_usd": cost_usd,
                "sources": list(sources),
            }
        )
        return row


def test_record_cash_from_event_writes_once() -> None:
    from midas.flagship.stripe_webhook import StripeEvent

    mem = _FakeMemory()
    event = StripeEvent(
        id="evt_first", type="checkout.session.completed", livemode=False,
        payment_link_id="plink_x", payment_intent_id="pi_77",
        amount_received=4900, currency="usd", customer_email="",
    )
    assert record_cash_from_event(mem, event) is True
    call = mem.cash_calls[0]
    assert call["key"] == "evt_first"
    assert call["channel"] == "stripe"
    assert call["offer"] == "plink_x"
    assert call["revenue_usd"] == 49.0
    assert call["sources"] == ["https://dashboard.stripe.com/payments/pi_77"]


def test_record_cash_from_event_is_idempotent() -> None:
    from midas.flagship.stripe_webhook import StripeEvent

    mem = _FakeMemory()
    event = StripeEvent(
        id="evt_dup", type="payment_intent.succeeded", livemode=False,
        payment_link_id="", payment_intent_id="pi_88",
        amount_received=1000, currency="usd", customer_email="",
    )
    assert record_cash_from_event(mem, event) is True
    # Same event twice → second call must no-op.
    assert record_cash_from_event(mem, event) is False
    assert len(mem.cash_calls) == 1


def test_record_cash_from_event_handles_jpy_zero_decimal() -> None:
    from midas.flagship.stripe_webhook import StripeEvent

    mem = _FakeMemory()
    event = StripeEvent(
        id="evt_jpy", type="checkout.session.completed", livemode=False,
        payment_link_id="", payment_intent_id="pi_jpy",
        amount_received=5000, currency="jpy", customer_email="",
    )
    record_cash_from_event(mem, event)
    # JPY: 5000 minor units = 5000 yen (no /100 conversion).
    assert mem.cash_calls[0]["revenue_usd"] == 5000.0
