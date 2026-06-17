"""Stripe payment link tool — closes the cash loop.

Before this tool, the agent could draft a proposal/quote/invoice but had no way
to actually collect the cash without manual operator work. ``stripe.payment_link``
fills that gap: it queues an approval describing the line items + amount +
currency; on approval the executor calls Stripe and returns a hosted payment URL
the operator can ship to the buyer.

Contract
--------
- Plan validates amount / currency / description. NO egress, NO secret read.
- The approval payload carries the canonical intent + sha256_intent.
- Executor reads ``STRIPE_API_KEY`` from environment (operator's key, never
  ours), calls ``/v1/payment_links``, and records a receipt with the resulting
  ``payment_link_id`` + ``url`` + ``amount_usd`` so per-run ROI joins.
- Stub backend (always available, no egress) is used by tests and dry-runs.

Security envelope
-----------------
- Action: ``publish_public`` — APPROVE-tier (already in default policy).
- Egress at execute time only. Output is ``Taint.UNTRUSTED``.
- ``STRIPE_API_KEY`` is read from env at execute time only — a planned-but-not-
  approved request can never see it.
- The link URL is what we return to the caller; we never log the API key.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class StripeBackendError(RuntimeError):
    """Raised when the Stripe backend can't satisfy the request."""


@dataclass(frozen=True)
class PaymentLinkResult:
    """Flat shape stored in the receipt."""

    payment_link_id: str
    url: str
    amount_minor: int  # smallest currency unit (cents for USD/EUR)
    currency: str
    raw_status: str = ""


class StripeBackend(Protocol):
    name: str

    def create_payment_link(
        self,
        *,
        description: str,
        amount_minor: int,
        currency: str,
        product_name: str,
    ) -> PaymentLinkResult: ...


_CURRENCY_MIN_AMOUNT = {
    # Stripe minimum charge varies by currency. We enforce the common floors.
    "usd": 50,
    "eur": 50,
    "cad": 50,
    "gbp": 30,
    "jpy": 50,
}
_MAX_MINOR = 99_999_99  # $99,999.99 — sanity cap; agents should not propose larger


@dataclass
class StripePaymentLinkPlan:
    """Approval payload — describes the link to create, not the link itself."""

    kind: str  # always "stripe_payment_link"
    description: str
    product_name: str
    amount_minor: int
    currency: str
    sha256_intent: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


def _hash_intent(
    *, description: str, product_name: str, amount_minor: int, currency: str
) -> str:
    canonical = f"{currency}|{amount_minor}|{product_name}|{description}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_minor(amount: float, currency: str) -> int:
    """Currency-aware conversion to Stripe's smallest-unit integer.

    JPY is zero-decimal in Stripe; everything else we use is two-decimal.
    """
    if currency == "jpy":
        return int(round(amount))
    return int(round(amount * 100))


def plan_payment_link(
    *,
    description: str,
    amount_usd: float,
    currency: str = "USD",
    product_name: str = "",
) -> StripePaymentLinkPlan:
    """Build the approval payload. No egress, no secret read."""
    if not description.strip():
        raise ValueError("stripe.payment_link needs a non-empty description")
    cur = currency.strip().lower()
    if cur not in _CURRENCY_MIN_AMOUNT:
        raise ValueError(
            f"unsupported currency {currency!r}; supported: "
            f"{sorted(_CURRENCY_MIN_AMOUNT)}"
        )
    if amount_usd <= 0:
        raise ValueError(f"amount must be positive, got {amount_usd}")
    minor = _to_minor(amount_usd, cur)
    min_floor = _CURRENCY_MIN_AMOUNT[cur]
    if minor < min_floor:
        raise ValueError(
            f"amount below Stripe minimum for {cur}: {minor} < {min_floor}"
        )
    if minor > _MAX_MINOR:
        raise ValueError(f"amount above sanity cap: {minor} > {_MAX_MINOR}")
    product = product_name.strip() or description.strip()[:80]
    intent = _hash_intent(
        description=description,
        product_name=product,
        amount_minor=minor,
        currency=cur,
    )
    return StripePaymentLinkPlan(
        kind="stripe_payment_link",
        description=description.strip(),
        product_name=product,
        amount_minor=minor,
        currency=cur,
        sha256_intent=intent,
        preview=f"{cur.upper()} {amount_usd:.2f} — {product}",
        meta={"amount_usd": amount_usd},
    )


# ── backends ─────────────────────────────────────────────────────────────────


_BACKENDS: dict[str, StripeBackend] = {}


def register_backend(backend: StripeBackend) -> None:
    _BACKENDS[backend.name] = backend


def get_backend(name: str = "stripe") -> StripeBackend | None:
    return _BACKENDS.get(name)


def execute_payment_link(
    payload: dict[str, Any], *, backend_name: str = "stripe"
) -> PaymentLinkResult:
    """Post-approval executor. Reads STRIPE_API_KEY at this step only."""
    description = str(payload.get("description") or "")
    product_name = str(payload.get("product_name") or "")
    amount_minor = int(payload.get("amount_minor") or 0)
    currency = str(payload.get("currency") or "").lower()
    if not description or not product_name or amount_minor <= 0 or not currency:
        raise ValueError("stripe.payment_link payload is missing required fields")

    expected = str(payload.get("sha256_intent") or "")
    if expected:
        got = _hash_intent(
            description=description,
            product_name=product_name,
            amount_minor=amount_minor,
            currency=currency,
        )
        if got != expected:
            raise StripeBackendError(
                "stripe.payment_link refused: payload intent hash drifted"
            )

    backend = _BACKENDS.get(backend_name)
    if backend is None:
        raise StripeBackendError(
            f"no stripe backend registered for {backend_name!r}; "
            f"available: {sorted(_BACKENDS)}"
        )
    return backend.create_payment_link(
        description=description,
        amount_minor=amount_minor,
        currency=currency,
        product_name=product_name,
    )


# ── stub backend (always available, no egress) ───────────────────────────────


@dataclass
class StubStripeBackend:
    """Deterministic, no-egress backend for tests + dry-runs."""

    name: str = "stub"

    def create_payment_link(
        self,
        *,
        description: str,
        amount_minor: int,
        currency: str,
        product_name: str,
    ) -> PaymentLinkResult:
        digest = hashlib.sha256(
            f"{currency}|{amount_minor}|{product_name}".encode()
        ).hexdigest()[:24]
        return PaymentLinkResult(
            payment_link_id=f"plink_stub_{digest}",
            url=f"stub://stripe/checkout/{digest}",
            amount_minor=amount_minor,
            currency=currency,
            raw_status="stub_ok",
        )


# ── real Stripe backend (opt-in, requires STRIPE_API_KEY) ────────────────────


@dataclass
class StripeBackendImpl:
    """Calls the real Stripe REST API. Requires STRIPE_API_KEY at execute time.

    We deliberately use ``httpx`` form-encoded calls rather than the official
    ``stripe`` SDK to avoid pinning yet another heavy dependency. Stripe's API
    is form-encoded by spec, so this is faithful, not a workaround.
    """

    name: str = "stripe"

    def create_payment_link(
        self,
        *,
        description: str,
        amount_minor: int,
        currency: str,
        product_name: str,
    ) -> PaymentLinkResult:
        api_key = os.environ.get("STRIPE_API_KEY")
        if not api_key:
            raise StripeBackendError(
                "stripe backend needs STRIPE_API_KEY in the environment"
            )
        if not api_key.startswith(("sk_", "rk_")):
            # Honest refusal — a publishable key (pk_...) can't create
            # payment links. Catching this early avoids a confusing 401.
            raise StripeBackendError(
                "stripe API key must be secret/restricted (sk_ or rk_), "
                "not a publishable key (pk_)"
            )
        try:
            import httpx
        except ImportError as e:
            raise StripeBackendError(
                "stripe backend needs httpx; install with `pip install httpx`"
            ) from e

        # Two API calls: create a price (with inline product), then a payment
        # link from that price. Both endpoints are form-encoded.
        try:
            price_resp = httpx.post(
                "https://api.stripe.com/v1/prices",
                auth=(api_key, ""),
                data={
                    "currency": currency,
                    "unit_amount": str(amount_minor),
                    "product_data[name]": product_name[:250],
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise StripeBackendError(f"stripe price request failed: {e}") from e
        if price_resp.status_code != 200:
            raise StripeBackendError(
                f"stripe /v1/prices returned {price_resp.status_code}: "
                f"{price_resp.text[:200]}"
            )
        price_id = (price_resp.json() or {}).get("id")
        if not price_id:
            raise StripeBackendError("stripe /v1/prices response is missing id")

        try:
            link_resp = httpx.post(
                "https://api.stripe.com/v1/payment_links",
                auth=(api_key, ""),
                data={
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": "1",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise StripeBackendError(f"stripe payment_link request failed: {e}") from e
        if link_resp.status_code != 200:
            raise StripeBackendError(
                f"stripe /v1/payment_links returned {link_resp.status_code}: "
                f"{link_resp.text[:200]}"
            )
        link = link_resp.json() or {}
        link_id = link.get("id")
        url = link.get("url")
        if not link_id or not url:
            raise StripeBackendError(
                "stripe /v1/payment_links response is missing id or url"
            )
        return PaymentLinkResult(
            payment_link_id=str(link_id),
            url=str(url),
            amount_minor=amount_minor,
            currency=currency,
            raw_status="stripe_ok",
        )


# Stub registered unconditionally so tests + dry-runs work without creds.
# The real Stripe backend is registered by the runtime — see runtime.py.
register_backend(StubStripeBackend())


def register_default_backends() -> None:
    register_backend(StripeBackendImpl())
