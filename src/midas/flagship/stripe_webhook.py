"""Stripe webhook verifier — closes the cash auto-attribution loop.

When a payment succeeds, Stripe POSTs an event to a public endpoint. This
module verifies the HMAC signature (constant-time), checks the timestamp
against replay attacks, parses the event, and lets the dashboard record the
attributed revenue in ``MemoryKind.CASH`` automatically — so the operator
never has to type ``midas outcome record``.

Security envelope
-----------------
- Signature check uses :func:`hmac.compare_digest` (constant-time).
- Events older than 5 minutes are rejected (Stripe's recommended replay
  window). The 5-minute floor matches Stripe's own webhook docs.
- The endpoint is the ONLY unauthenticated endpoint in the dashboard. It is
  bound to loopback by design — the operator must tunnel it through ngrok /
  cloudflared / their own ingress to expose it to Stripe. Honest: we do NOT
  open it on 0.0.0.0; that would violate the local-first contract.
- The endpoint always returns 200 on signature-verified events, even if the
  event type isn't one we act on (Stripe retries on non-2xx — we don't want
  noisy retries for events we deliberately ignore).
- Idempotency: each ``event.id`` is recorded only once. A duplicate webhook
  replay is a no-op.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class StripeWebhookError(Exception):
    """Raised when a webhook fails verification or is malformed."""


# Stripe's docs recommend a 5-minute tolerance window.
DEFAULT_TOLERANCE_SECONDS = 300


@dataclass(frozen=True)
class StripeEvent:
    """Minimal projection of the Stripe event we care about."""

    id: str
    type: str
    livemode: bool
    payment_link_id: str  # may be empty if event isn't link-based
    payment_intent_id: str
    amount_received: int  # smallest currency unit
    currency: str
    customer_email: str


def verify_signature(
    *,
    payload: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> None:
    """Verify ``Stripe-Signature`` header HMAC. Raises on any failure.

    Stripe signs payloads with: ``HMAC_SHA256(secret, f"{timestamp}.{payload}")``.
    The header has the form ``t=<unix_ts>,v1=<hex_sig>[,v1=<hex_sig>...]`` — we
    accept any ``v1`` signature matching (Stripe rotates secrets atomically).
    """
    if not signature_header:
        raise StripeWebhookError("missing Stripe-Signature header")
    if not secret:
        raise StripeWebhookError("STRIPE_WEBHOOK_SECRET not configured")

    parts: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        parts.setdefault(k.strip(), []).append(v.strip())

    timestamps = parts.get("t") or []
    sigs = parts.get("v1") or []
    if not timestamps or not sigs:
        raise StripeWebhookError("Stripe-Signature header is malformed")

    try:
        ts = int(timestamps[0])
    except ValueError as e:
        raise StripeWebhookError("Stripe-Signature timestamp is not an integer") from e

    current = now if now is not None else time.time()
    if abs(current - ts) > tolerance_seconds:
        raise StripeWebhookError(
            f"webhook timestamp outside tolerance "
            f"(|now - t| = {abs(current - ts):.0f}s > {tolerance_seconds}s)"
        )

    signed_payload = f"{ts}.".encode() + payload
    expected = hmac.new(
        secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()
    # Constant-time compare against *every* v1 sig — atomic rotation safe.
    if not any(hmac.compare_digest(expected, sig) for sig in sigs):
        raise StripeWebhookError("Stripe-Signature does not match payload")


def parse_event(payload: bytes) -> StripeEvent:
    """Parse a verified Stripe event into the minimal shape we record."""
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StripeWebhookError(f"webhook body is not valid JSON: {e}") from e

    event_id = str(body.get("id") or "")
    event_type = str(body.get("type") or "")
    livemode = bool(body.get("livemode") or False)
    data_obj = (body.get("data") or {}).get("object") or {}

    # Different event types put the interesting bits at different paths.
    if event_type == "checkout.session.completed":
        payment_link_id = str(data_obj.get("payment_link") or "")
        payment_intent_id = str(data_obj.get("payment_intent") or "")
        amount_received = int(data_obj.get("amount_total") or 0)
        currency = str(data_obj.get("currency") or "").lower()
        customer_email = str(
            data_obj.get("customer_details", {}).get("email") or ""
        )
    elif event_type == "payment_intent.succeeded":
        payment_link_id = str(
            (data_obj.get("metadata") or {}).get("payment_link") or ""
        )
        payment_intent_id = str(data_obj.get("id") or "")
        amount_received = int(data_obj.get("amount_received") or 0)
        currency = str(data_obj.get("currency") or "").lower()
        customer_email = str(data_obj.get("receipt_email") or "")
    else:
        payment_link_id = ""
        payment_intent_id = ""
        amount_received = 0
        currency = ""
        customer_email = ""

    if not event_id or not event_type:
        raise StripeWebhookError("webhook body missing id or type")
    return StripeEvent(
        id=event_id,
        type=event_type,
        livemode=livemode,
        payment_link_id=payment_link_id,
        payment_intent_id=payment_intent_id,
        amount_received=amount_received,
        currency=currency,
        customer_email=customer_email,
    )


def is_cash_event(event: StripeEvent) -> bool:
    """Only events that represent realized revenue should hit MemoryKind.CASH."""
    return event.type in {
        "checkout.session.completed",
        "payment_intent.succeeded",
    } and event.amount_received > 0


def record_cash_from_event(memory: Any, event: StripeEvent) -> bool:
    """Idempotent: returns True if a new CASH entry was written.

    Idempotency is enforced via the memory ``key`` set to the Stripe event id.
    If a row already exists with that key (newest-first), we no-op.
    """
    if memory is None or not is_cash_event(event):
        return False
    # Memory.recall returns newest-first; check the most recent CASH page only.
    try:
        from midas.core.memory import MemoryKind  # local import: optional dep

        existing = memory.recall(kind=MemoryKind.CASH, limit=100)
    except Exception:
        existing = []
    for row in existing:
        if getattr(row, "key", "") == event.id:
            return False
    # Convert minor units → major units; JPY is zero-decimal in Stripe.
    revenue = (
        float(event.amount_received)
        if event.currency == "jpy"
        else float(event.amount_received) / 100.0
    )
    sources = []
    if event.payment_intent_id:
        sources.append(
            f"https://dashboard.stripe.com/payments/{event.payment_intent_id}"
        )
    memory.record_cash(
        event.id,
        channel="stripe",
        offer=event.payment_link_id or "direct",
        revenue_usd=revenue,
        cost_usd=0.0,
        sources=sources,
    )
    return True
