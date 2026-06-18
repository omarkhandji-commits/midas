"""affiliate.link.generate — build tracked affiliate links honestly.

Why
---
Affiliate revenue is a recurring cash vein for content creators and
consultants. The mechanics aren't magic: a tracked URL carries a unique
identifier so the merchant can attribute the sale. This tool builds the
URL with the operator's chosen UTM parameters and a campaign-specific
slug, returning a sha256 the operator can also record as a memory entry
to later reconcile against Stripe (or the merchant's affiliate dashboard).

Contract
--------
- AUTO-tier (``read_local_files``). Pure URL construction, no egress.
- Validates the merchant URL is absolute http(s).
- Refuses to silently overwrite an existing UTM parameter — the planner
  must clear the merchant URL first if they really want to override.
- Output ``Taint.TRUSTED`` — the URL is built by us, not pulled from a
  third party.

Honest constraints
------------------
- We do NOT cloak the URL. Affiliate disclosure is required in most
  jurisdictions (FTC, ASA, EU UCPD). Cloaking the URL makes that
  disclosure harder; the agent's output is plain.
- We do NOT inject pixel trackers, cookies, or fingerprints — that's
  the merchant's job, not ours.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class AffiliateError(RuntimeError):
    """Raised when an affiliate link can't be built honestly."""


_RESERVED_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


@dataclass(frozen=True)
class AffiliateLink:
    url: str
    sha256: str
    merchant: str  # netloc of the merchant
    campaign: str
    utm: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "merchant": self.merchant,
            "campaign": self.campaign,
            "utm": dict(self.utm),
        }


def _clean_utm(value: str) -> str:
    """UTM values: trim, lowercase, ASCII-safe-ish. Surface nothing weird."""
    return value.strip().replace(" ", "_")


def generate_affiliate_link(
    *,
    merchant_url: str,
    campaign: str,
    source: str = "midas",
    medium: str = "referral",
    content: str = "",
    term: str = "",
    extra_params: dict[str, str] | None = None,
) -> AffiliateLink:
    """Append UTM parameters to ``merchant_url`` and return the tracked link."""
    parsed = urlparse(merchant_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AffiliateError(
            f"affiliate.link.generate needs absolute http(s) URL, got {merchant_url!r}"
        )
    campaign = _clean_utm(campaign)
    if not campaign:
        raise AffiliateError("affiliate.link.generate needs a non-empty campaign")

    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # Refuse silent overwrites of UTM the merchant URL already carries — that
    # is almost always a mistake by the planner.
    for k in _RESERVED_PARAMS:
        if k in existing:
            raise AffiliateError(
                f"merchant URL already carries {k!r}; clear it before adding our own"
            )

    utm: dict[str, str] = {
        "utm_source": _clean_utm(source) or "midas",
        "utm_medium": _clean_utm(medium) or "referral",
        "utm_campaign": campaign,
    }
    if content:
        utm["utm_content"] = _clean_utm(content)
    if term:
        utm["utm_term"] = _clean_utm(term)
    if extra_params:
        for k, v in extra_params.items():
            key = str(k).strip()
            if not key:
                continue
            if key in utm:
                raise AffiliateError(
                    f"extra_params overrides reserved key {key!r}"
                )
            utm[key] = str(v).strip()

    merged = {**existing, **utm}
    query = urlencode(merged, doseq=False)
    rebuilt = urlunparse((
        parsed.scheme, parsed.netloc, parsed.path,
        parsed.params, query, parsed.fragment,
    ))
    return AffiliateLink(
        url=rebuilt,
        sha256=hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
        merchant=parsed.netloc,
        campaign=campaign,
        utm=utm,
    )
