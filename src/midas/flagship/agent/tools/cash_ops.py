"""Small cash-ops primitives used by the agent and dashboard."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

LifecycleStatus = Literal["lead", "won", "lost", "churned"]


@dataclass(frozen=True)
class ReferralCode:
    customer_key: str
    code: str
    commission_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "customer_key": self.customer_key,
            "code": self.code,
            "commission_rate": self.commission_rate,
        }


@dataclass(frozen=True)
class ReferralPayout:
    code: str
    attributed_revenue: float
    commission_rate: float
    payout: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "attributed_revenue": self.attributed_revenue,
            "commission_rate": self.commission_rate,
            "payout": self.payout,
        }


@dataclass(frozen=True)
class LifecycleTransition:
    customer_key: str
    status: LifecycleStatus
    previous_status: str
    reason: str
    ts: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "customer_key": self.customer_key,
            "status": self.status,
            "previous_status": self.previous_status,
            "reason": self.reason,
            "ts": self.ts,
        }


@dataclass(frozen=True)
class CohortReport:
    cohorts: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"cohorts": self.cohorts}


def generate_referral_code(
    customer_key: str,
    *,
    prefix: str = "MIDAS",
    commission_rate: float = 0.10,
) -> ReferralCode:
    if not customer_key.strip():
        raise ValueError("referral.code.generate needs a customer_key")
    if commission_rate < 0 or commission_rate > 1:
        raise ValueError("commission_rate must be between 0 and 1")
    digest = hashlib.sha256(customer_key.strip().lower().encode("utf-8")).hexdigest()[:8]
    clean_prefix = "".join(ch for ch in prefix.upper() if ch.isalnum())[:10] or "MIDAS"
    return ReferralCode(
        customer_key=customer_key.strip(),
        code=f"{clean_prefix}-{digest.upper()}",
        commission_rate=round(float(commission_rate), 4),
    )


def compute_referral_payout(
    code: str,
    *,
    attributed_revenue: float,
    commission_rate: float,
) -> ReferralPayout:
    if not code.strip():
        raise ValueError("referral.payout.compute needs a code")
    if attributed_revenue < 0:
        raise ValueError("attributed_revenue cannot be negative")
    if commission_rate < 0 or commission_rate > 1:
        raise ValueError("commission_rate must be between 0 and 1")
    payout = round(float(attributed_revenue) * float(commission_rate), 2)
    return ReferralPayout(
        code=code.strip(),
        attributed_revenue=round(float(attributed_revenue), 2),
        commission_rate=round(float(commission_rate), 4),
        payout=payout,
    )


def transition_customer_lifecycle(
    customer_key: str,
    *,
    status: LifecycleStatus,
    previous_status: str = "",
    reason: str = "",
) -> LifecycleTransition:
    if not customer_key.strip():
        raise ValueError("customer.lifecycle needs a customer_key")
    if status not in {"lead", "won", "lost", "churned"}:
        raise ValueError("status must be lead, won, lost, or churned")
    return LifecycleTransition(
        customer_key=customer_key.strip(),
        status=status,
        previous_status=previous_status.strip(),
        reason=reason.strip(),
        ts=datetime.now(UTC).isoformat(),
    )


def build_upsell_sequence(
    *,
    product: str,
    customer_segment: str,
    next_offer: str,
    days: list[int] | None = None,
) -> dict[str, Any]:
    if not product.strip() or not next_offer.strip():
        raise ValueError("upsell.sequence needs product and next_offer")
    schedule = days or [1, 7, 21]
    steps = []
    for day in schedule:
        steps.append(
            {
                "day": int(day),
                "subject": f"Next step after {product.strip()}",
                "body": (
                    f"For {customer_segment.strip() or 'this customer'}, offer "
                    f"{next_offer.strip()} only if the original purchase is delivered."
                ),
            }
        )
    return {
        "product": product.strip(),
        "customer_segment": customer_segment.strip(),
        "next_offer": next_offer.strip(),
        "steps": steps,
        "trigger": "stripe.payment_succeeded",
        "approval_required_before_send": True,
    }


def compute_cohort_retention(events: list[dict[str, Any]]) -> CohortReport:
    """Compute weekly retention from event dicts.

    Expected event shape: customer_id, cohort_week, active_week. Values are
    strings such as 2026-W25. Unknown rows are ignored.
    """
    cohorts: dict[str, dict[str, set[str]]] = {}
    for event in events:
        customer = str(event.get("customer_id") or "").strip()
        cohort = str(event.get("cohort_week") or "").strip()
        active = str(event.get("active_week") or "").strip()
        if not customer or not cohort or not active:
            continue
        weeks = cohorts.setdefault(cohort, {})
        weeks.setdefault(active, set()).add(customer)
    rows: list[dict[str, Any]] = []
    for cohort, weeks in sorted(cohorts.items()):
        base = len(weeks.get(cohort, set())) or len(set().union(*weeks.values()))
        retention = []
        for week, customers in sorted(weeks.items()):
            retention.append(
                {
                    "week": week,
                    "active_customers": len(customers),
                    "retention": round(len(customers) / base, 4) if base else 0.0,
                }
            )
        rows.append({"cohort_week": cohort, "size": base, "retention": retention})
    return CohortReport(rows)
