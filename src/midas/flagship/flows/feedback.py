"""Feedback → scoring: bias next scan's factors from what already paid (or didn't).

Reads RESULT, CASH and ERROR memories and produces a small, **bounded, explicit**
adjustment to FactorScores. Never invents numbers: if no past evidence, returns the
zero vector. The planner can apply this nudge before scoring next niches, so the
loop visibly *learns from cash*.

Why this exists. The HANDOFF already has scan → score → prepare → outcome, but
nothing closes the feedback edge: outcomes never bias the next scan. This module
is that edge.

Adjustment policy (kept simple on purpose — additive nudges, capped):

- CASH entry with net > 0 → ``distribution += +1``, ``speed_to_cash += +1`` (max +2).
- ERROR/RESULT containing "no reply" / "no sale" → ``distribution -= 1`` (max -2).

Each factor stays in [0, 10] after adjustment. We never mutate the original
FactorScores — we return a *new* one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from midas.flagship.scoring import FactorScores

_MAX_DELTA_PER_FACTOR = 2.0


@dataclass(frozen=True)
class FeedbackAdjustment:
    """Bounded, explicit nudge derived from past memories. All deltas in [-2, +2]."""

    deltas: dict[str, float]
    reasons: list[str]

    @property
    def is_zero(self) -> bool:
        return not self.deltas or all(abs(v) < 1e-9 for v in self.deltas.values())


def feedback_factors(memory: Any, *, niche: str | None = None) -> FeedbackAdjustment:
    """Compute a bounded adjustment from CASH/RESULT/ERROR memories.

    ``niche`` is currently ignored for the lookup (we recall all CASH/RESULT/ERROR
    rows); the bias is intentionally coarse. Refining by niche belongs in V2 if
    proven useful.
    """
    if memory is None or not hasattr(memory, "recall"):
        return FeedbackAdjustment(deltas={}, reasons=[])

    from midas.core.memory import MemoryKind  # local import to avoid cycles

    deltas: dict[str, float] = {}
    reasons: list[str] = []

    def _bump(factor: str, amount: float) -> None:
        cur = deltas.get(factor, 0.0)
        # Clamp each factor's cumulative delta to [-MAX, +MAX].
        new = max(-_MAX_DELTA_PER_FACTOR, min(_MAX_DELTA_PER_FACTOR, cur + amount))
        deltas[factor] = new

    # CASH memories — positive net biases toward speed/distribution.
    try:
        cash_rows = memory.recall(kind=MemoryKind.CASH, limit=20)
    except Exception:  # noqa: BLE001 — never poison the planner
        cash_rows = []
    for row in cash_rows:
        content = (row.content or "").lower()
        # We stored "net=$N.NN"; positive net = a paying channel/offer.
        if "net=$-" in content:
            _bump("distribution", -1.0)
            reasons.append(f"past loss on {row.key}")
        elif "net=$" in content:
            _bump("distribution", +1.0)
            _bump("speed_to_cash", +1.0)
            reasons.append(f"past win on {row.key}")

    # RESULT / ERROR — coarse "no reply / no sale" signals depress distribution.
    for kind in (MemoryKind.RESULT, MemoryKind.ERROR):
        try:
            rows = memory.recall(kind=kind, limit=20)
        except Exception:  # noqa: BLE001
            rows = []
        for row in rows:
            txt = (row.content or "").lower()
            if any(needle in txt for needle in ("no reply", "no sale", "did not work")):
                _bump("distribution", -1.0)
                reasons.append(f"{kind.value}: '{row.key}' flagged as flat")

    return FeedbackAdjustment(deltas=deltas, reasons=reasons)


def apply_feedback(factors: FactorScores, adj: FeedbackAdjustment) -> FactorScores:
    """Return a NEW FactorScores with ``adj`` applied; clamped to [0, 10]."""
    if adj.is_zero:
        return factors
    raw = factors.model_dump()
    for k, dv in adj.deltas.items():
        if k in raw:
            raw[k] = max(0.0, min(10.0, float(raw[k]) + float(dv)))
    return FactorScores(**raw)
