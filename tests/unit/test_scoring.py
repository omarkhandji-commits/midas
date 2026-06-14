"""Scoring engine: reproduces the docs/SCORING.md worked example (~71.4) + bands + gates."""

from __future__ import annotations

from midas.flagship.scoring import Band, FactorScores, HardGates, score

# The worked example from docs/SCORING.md.
EXAMPLE = FactorScores(
    demand=8,
    speed_to_cash=7,
    mrr_potential=9,
    low_support=6,
    defensibility=5,
    low_competition=5,
    distribution=7,
    low_cost=8,
    low_launch_time=6,
    low_risk=8,
    operator_fit=8,
)


def test_golden_example_total_and_band() -> None:
    res = score(EXAMPLE)
    assert abs(res.total - 71.4) < 0.05
    assert res.band == Band.WATCHLIST


def test_weakest_factor_matches_doc() -> None:
    # SCORING.md names defensibility (lowest value, tie broken by canonical order).
    assert score(EXAMPLE).weakest_factor == "defensibility"


def test_high_scores_reach_build_band() -> None:
    great = FactorScores(**{k: 9 for k in EXAMPLE.model_dump()})
    res = score(great)
    assert res.total >= 75
    assert res.band == Band.BUILD


def test_low_scores_archive() -> None:
    poor = FactorScores(**{k: 3 for k in EXAMPLE.model_dump()})
    assert score(poor).band == Band.ARCHIVE


def test_hard_gate_forces_archive_despite_high_score() -> None:
    great = FactorScores(**{k: 10 for k in EXAMPLE.model_dump()})
    res = score(great, HardGates(structurally_high_support=True))
    assert res.band == Band.ARCHIVE
    assert res.archived_by_gate is not None
    assert res.total == 100.0  # the raw score is still reported, but the gate wins


def test_contributions_sum_to_total() -> None:
    res = score(EXAMPLE)
    assert abs(sum(res.contributions.values()) - res.total) < 1e-6
