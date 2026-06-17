"""Stripe payment link tool — closes the cash loop, approval-gated.

Same contract as social.publish: plan does NOT egress, executor verifies the
intent hash, real backend requires STRIPE_API_KEY only at execute time.
"""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.stripe_pay import (
    PaymentLinkResult,
    StripeBackendError,
    StripeBackendImpl,
    StubStripeBackend,
    _hash_intent,
    execute_payment_link,
    plan_payment_link,
    register_backend,
)


def test_plan_rejects_empty_description() -> None:
    with pytest.raises(ValueError, match="non-empty description"):
        plan_payment_link(description="   ", amount_usd=10.0)


def test_plan_rejects_unknown_currency() -> None:
    with pytest.raises(ValueError, match="unsupported currency"):
        plan_payment_link(
            description="Coaching call", amount_usd=10.0, currency="XYZ"
        )


def test_plan_rejects_zero_amount() -> None:
    with pytest.raises(ValueError, match="positive"):
        plan_payment_link(description="x", amount_usd=0)


def test_plan_rejects_below_stripe_minimum() -> None:
    with pytest.raises(ValueError, match="below Stripe minimum"):
        plan_payment_link(description="x", amount_usd=0.10, currency="USD")


def test_plan_rejects_above_sanity_cap() -> None:
    with pytest.raises(ValueError, match="sanity cap"):
        plan_payment_link(description="x", amount_usd=1_000_000)


def test_plan_to_minor_usd_two_decimal() -> None:
    plan = plan_payment_link(
        description="One coaching call",
        amount_usd=49.99,
        currency="USD",
    )
    assert plan.amount_minor == 4999
    assert plan.currency == "usd"
    assert plan.sha256_intent == _hash_intent(
        description="One coaching call",
        product_name="One coaching call",
        amount_minor=4999,
        currency="usd",
    )


def test_plan_to_minor_jpy_zero_decimal() -> None:
    plan = plan_payment_link(
        description="Consult", amount_usd=500, currency="JPY"
    )
    assert plan.amount_minor == 500  # JPY is zero-decimal in Stripe


def test_execute_uses_stub_backend() -> None:
    register_backend(StubStripeBackend())
    plan = plan_payment_link(
        description="Test product",
        amount_usd=49.0,
        currency="USD",
        product_name="Custom widget",
    )
    payload = {
        "description": plan.description,
        "product_name": plan.product_name,
        "amount_minor": plan.amount_minor,
        "currency": plan.currency,
        "sha256_intent": plan.sha256_intent,
    }
    result = execute_payment_link(payload, backend_name="stub")
    assert isinstance(result, PaymentLinkResult)
    assert result.payment_link_id.startswith("plink_stub_")
    assert result.url.startswith("stub://stripe/checkout/")
    assert result.amount_minor == 4900
    assert result.currency == "usd"


def test_execute_refuses_intent_drift() -> None:
    register_backend(StubStripeBackend())
    payload = {
        "description": "tampered desc",
        "product_name": "thing",
        "amount_minor": 9900,
        "currency": "usd",
        "sha256_intent": _hash_intent(
            description="original desc",
            product_name="thing",
            amount_minor=9900,
            currency="usd",
        ),
    }
    with pytest.raises(StripeBackendError, match="intent hash drifted"):
        execute_payment_link(payload, backend_name="stub")


def test_stripe_backend_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    backend = StripeBackendImpl()
    with pytest.raises(StripeBackendError, match="STRIPE_API_KEY"):
        backend.create_payment_link(
            description="x", amount_minor=1000, currency="usd", product_name="x"
        )


def test_stripe_backend_refuses_publishable_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pk_ key would 401; we catch it upfront with a clear message."""
    monkeypatch.setenv("STRIPE_API_KEY", "pk_live_fake")
    backend = StripeBackendImpl()
    with pytest.raises(StripeBackendError, match="publishable key"):
        backend.create_payment_link(
            description="x", amount_minor=1000, currency="usd", product_name="x"
        )
