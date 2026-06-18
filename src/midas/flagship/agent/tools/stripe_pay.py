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


@dataclass(frozen=True)
class StripeCreateResult:
    """Flat result for post-approval Stripe create calls."""

    id: str
    object: str
    url: str = ""
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


@dataclass
class StripeProductDraftPlan:
    kind: str
    name: str
    description: str
    images: list[str]
    metadata: dict[str, str]
    sha256_intent: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StripePriceDraftPlan:
    kind: str
    product: str
    unit_amount_minor: int
    currency: str
    recurring_interval: str | None
    lookup_key: str
    metadata: dict[str, str]
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


def _hash_payload(prefix: str, payload: dict[str, Any]) -> str:
    import json

    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{prefix}|{body}".encode()).hexdigest()


def plan_stripe_product_draft(
    *,
    name: str,
    description: str = "",
    images: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> StripeProductDraftPlan:
    """Build an approval payload for creating a Stripe product. No egress."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("stripe.product.draft needs a non-empty name")
    clean_images = [str(img).strip() for img in (images or []) if str(img).strip()]
    if len(clean_images) > 8:
        raise ValueError("stripe.product.draft accepts at most 8 images")
    clean_meta = _clean_metadata(metadata or {})
    intent_payload: dict[str, Any] = {
        "name": clean_name,
        "description": description.strip(),
        "images": clean_images,
        "metadata": clean_meta,
    }
    return StripeProductDraftPlan(
        kind="stripe_product",
        name=clean_name,
        description=description.strip(),
        images=clean_images,
        metadata=clean_meta,
        sha256_intent=_hash_payload("stripe.product", intent_payload),
        preview=f"Create Stripe product: {clean_name}",
        meta={"n_images": len(clean_images), "n_metadata": len(clean_meta)},
    )


def plan_stripe_price_draft(
    *,
    product: str,
    unit_amount: float,
    currency: str = "USD",
    recurring_interval: str | None = None,
    lookup_key: str = "",
    metadata: dict[str, str] | None = None,
) -> StripePriceDraftPlan:
    """Build an approval payload for a one-time or recurring Stripe price."""
    product_id = product.strip()
    if not product_id:
        raise ValueError("stripe.price.draft needs a product id")
    cur = currency.strip().lower()
    if cur not in _CURRENCY_MIN_AMOUNT:
        raise ValueError(
            f"unsupported currency {currency!r}; supported: {sorted(_CURRENCY_MIN_AMOUNT)}"
        )
    interval = recurring_interval.strip().lower() if recurring_interval else None
    if interval == "":
        interval = None
    if interval not in {None, "month", "year"}:
        raise ValueError("recurring_interval must be 'month', 'year', or omitted")
    minor = _to_minor(float(unit_amount), cur)
    min_floor = _CURRENCY_MIN_AMOUNT[cur]
    if minor < min_floor:
        raise ValueError(f"amount below Stripe minimum for {cur}: {minor} < {min_floor}")
    if minor > _MAX_MINOR:
        raise ValueError(f"amount above sanity cap: {minor} > {_MAX_MINOR}")
    clean_meta = _clean_metadata(metadata or {})
    lookup = lookup_key.strip() or _default_lookup_key(product_id, minor, cur, interval)
    intent_payload: dict[str, Any] = {
        "product": product_id,
        "unit_amount_minor": minor,
        "currency": cur,
        "recurring_interval": interval,
        "lookup_key": lookup,
        "metadata": clean_meta,
    }
    cadence = f"/{interval}" if interval else " one-time"
    return StripePriceDraftPlan(
        kind="stripe_price",
        product=product_id,
        unit_amount_minor=minor,
        currency=cur,
        recurring_interval=interval,
        lookup_key=lookup,
        metadata=clean_meta,
        sha256_intent=_hash_payload("stripe.price", intent_payload),
        preview=f"Create Stripe price: {cur.upper()} {unit_amount:.2f}{cadence}",
        meta={"amount": float(unit_amount), "n_metadata": len(clean_meta)},
    )


def execute_product_draft(payload: dict[str, Any]) -> StripeCreateResult:
    product_payload = {
        "name": str(payload.get("name") or ""),
        "description": str(payload.get("description") or ""),
        "images": [str(x) for x in (payload.get("images") or [])],
        "metadata": {str(k): str(v) for k, v in (payload.get("metadata") or {}).items()},
    }
    if not product_payload["name"]:
        raise StripeBackendError("stripe.product.draft payload missing name")
    _assert_payload_hash("stripe.product", product_payload, payload)
    result = _stripe_post("/v1/products", _flatten_product_payload(product_payload))
    product_id = str(result.get("id") or "")
    if not product_id:
        raise StripeBackendError("stripe product response missing id")
    return StripeCreateResult(id=product_id, object="product", raw_status="stripe_ok")


def execute_price_draft(payload: dict[str, Any]) -> StripeCreateResult:
    interval = payload.get("recurring_interval")
    interval = str(interval) if interval else None
    product = str(payload.get("product") or "")
    amount_minor = int(payload.get("unit_amount_minor") or 0)
    price_payload = {
        "product": product,
        "unit_amount_minor": amount_minor,
        "currency": str(payload.get("currency") or "").lower(),
        "recurring_interval": interval,
        "lookup_key": str(payload.get("lookup_key") or ""),
        "metadata": {str(k): str(v) for k, v in (payload.get("metadata") or {}).items()},
    }
    if not product or amount_minor <= 0:
        raise StripeBackendError("stripe.price.draft payload missing product or amount")
    _assert_payload_hash("stripe.price", price_payload, payload)
    result = _stripe_post("/v1/prices", _flatten_price_payload(price_payload))
    price_id = str(result.get("id") or "")
    if not price_id:
        raise StripeBackendError("stripe price response missing id")
    return StripeCreateResult(id=price_id, object="price", raw_status="stripe_ok")


def _clean_metadata(metadata: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in metadata.items():
        k = str(key).strip()
        if not k:
            continue
        if len(k) > 40:
            raise ValueError(f"metadata key too long: {k[:20]}...")
        clean[k] = str(value).strip()[:500]
    return clean


def _default_lookup_key(
    product: str, amount_minor: int, currency: str, interval: str | None
) -> str:
    digest = hashlib.sha256(
        f"{product}|{amount_minor}|{currency}|{interval or 'once'}".encode()
    ).hexdigest()[:12]
    return f"midas_{currency}_{amount_minor}_{digest}"


def _assert_payload_hash(
    prefix: str, intent_payload: dict[str, Any], approval_payload: dict[str, Any]
) -> None:
    expected = str(approval_payload.get("sha256_intent") or "")
    if expected and _hash_payload(prefix, intent_payload) != expected:
        raise StripeBackendError(f"{prefix} refused: payload intent hash drifted")


def _flatten_product_payload(payload: dict[str, Any]) -> dict[str, str]:
    data = {"name": str(payload["name"])}
    if payload.get("description"):
        data["description"] = str(payload["description"])
    for i, image in enumerate(payload.get("images") or []):
        data[f"images[{i}]"] = str(image)
    for key, value in (payload.get("metadata") or {}).items():
        data[f"metadata[{key}]"] = str(value)
    return data


def _flatten_price_payload(payload: dict[str, Any]) -> dict[str, str]:
    data = {
        "product": str(payload["product"]),
        "unit_amount": str(payload["unit_amount_minor"]),
        "currency": str(payload["currency"]),
        "lookup_key": str(payload["lookup_key"]),
    }
    if payload.get("recurring_interval"):
        data["recurring[interval]"] = str(payload["recurring_interval"])
    for key, value in (payload.get("metadata") or {}).items():
        data[f"metadata[{key}]"] = str(value)
    return data


def _stripe_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    api_key = os.environ.get("STRIPE_API_KEY")
    if not api_key:
        raise StripeBackendError("Stripe execution needs STRIPE_API_KEY")
    if not api_key.startswith(("sk_", "rk_")):
        raise StripeBackendError("Stripe API key must be sk_ or rk_, not publishable")
    try:
        import httpx
    except ImportError as e:
        raise StripeBackendError("Stripe execution needs httpx") from e
    try:
        resp = httpx.post(
            f"https://api.stripe.com{path}",
            auth=(api_key, ""),
            data=data,
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise StripeBackendError(f"Stripe request failed: {e}") from e
    if resp.status_code != 200:
        raise StripeBackendError(
            f"Stripe {path} returned {resp.status_code}: {resp.text[:200]}"
        )
    return dict(resp.json() or {})
