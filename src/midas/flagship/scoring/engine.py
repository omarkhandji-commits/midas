"""Compute the /100 opportunity score with a transparent per-factor breakdown."""

from __future__ import annotations

from .models import Band, FactorScores, HardGates, ScoreBreakdown
from .weights import BUILD_MIN, WATCHLIST_MIN, WEIGHTS

_GATE_REASONS: dict[str, str] = {
    "requires_deception": "requires spam / deception / guaranteed-income claims",
    "legally_gray_or_pii": "legally gray or PII-scraping dependent",
    "structurally_high_support": "structurally high support",
    "no_distribution_channel": "no reachable distribution channel",
}


def _failed_gate(gates: HardGates | None) -> str | None:
    if gates is None:
        return None
    for field_name, reason in _GATE_REASONS.items():
        if getattr(gates, field_name):
            return reason
    return None


def score(factors: FactorScores, gates: HardGates | None = None) -> ScoreBreakdown:
    contributions = {k: getattr(factors, k) / 10.0 * w for k, w in WEIGHTS.items()}
    total = round(sum(contributions.values()), 4)

    # Weakest factor = lowest raw value; ties broken by canonical WEIGHTS order.
    weakest = min(WEIGHTS.keys(), key=lambda k: getattr(factors, k))

    gate = _failed_gate(gates)
    if gate is not None:
        return ScoreBreakdown(total, Band.ARCHIVE, contributions, weakest, archived_by_gate=gate)

    if total >= BUILD_MIN:
        band = Band.BUILD
    elif total >= WATCHLIST_MIN:
        band = Band.WATCHLIST
    else:
        band = Band.ARCHIVE
    return ScoreBreakdown(total, band, contributions, weakest)
