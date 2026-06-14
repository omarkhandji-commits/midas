"""The /100 opportunity scoring weights (source of truth: docs/SCORING.md). Sum = 100."""

from __future__ import annotations

# Order matters: it is the canonical tie-break order for the "weakest factor".
WEIGHTS: dict[str, int] = {
    "demand": 15,
    "speed_to_cash": 12,
    "mrr_potential": 15,
    "low_support": 10,
    "defensibility": 8,
    "low_competition": 7,
    "distribution": 10,
    "low_cost": 6,
    "low_launch_time": 7,
    "low_risk": 5,
    "operator_fit": 5,
}

assert sum(WEIGHTS.values()) == 100, "scoring weights must sum to 100"

BUILD_MIN = 75.0
WATCHLIST_MIN = 60.0
