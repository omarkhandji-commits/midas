"""The Proof-First scan flow: score → proof-gated select → prepare → estimate → STOP.

Asserts the contract: the Daily Revenue Move is the top *proven* buildable candidate,
the flow abstains rather than surface an unsourced move, the estimate is never a
prediction, and the headline next action is left for human approval.
"""

from __future__ import annotations

from midas.core.agents.summary import Finding, ProofLevel
from midas.flagship.flows import run_scan
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import Band, FactorScores, HardGates

STRONG = FactorScores(
    demand=9, speed_to_cash=8, mrr_potential=9, low_support=8, defensibility=6,
    low_competition=7, distribution=8, low_cost=9, low_launch_time=8, low_risk=8, operator_fit=8,
)
WEAK = FactorScores(**{k: 3 for k in STRONG.model_dump()})


def _cand(name: str, factors, proof: ProofLevel, sourced=True, **kw) -> OpportunityCandidate:
    findings = []
    if proof != ProofLevel.LOW or sourced:
        src = ["reddit.com/r/x"] if sourced else []
        findings = [Finding(f"pain for {name}", proof, sources=src)]
    return OpportunityCandidate(name=name, summary="...", findings=findings, factors=factors, **kw)


def test_daily_move_is_top_proven_buildable() -> None:
    cands = [
        _cand("weak", WEAK, ProofLevel.HIGH),
        _cand("strong", STRONG, ProofLevel.HIGH),
    ]
    report = run_scan("ai tools for plumbers", cands)
    assert report.daily_move is not None
    assert report.daily_move.candidate.name == "strong"
    assert report.daily_move.breakdown.band == Band.BUILD
    assert report.shortlist[0].candidate.name == "strong"  # ranked by score


def test_approval_default_move_stops_before_action() -> None:
    report = run_scan("niche", [_cand("strong", STRONG, ProofLevel.HIGH)])
    move = report.daily_move
    assert move is not None
    assert move.next_action_requires_approval is True
    assert "Estimate, not a prediction" in move.estimate.note
    assert move.brief.steps  # assets prepared (drafts), not executed


def test_abstains_when_top_candidate_unproven() -> None:
    # Scores well but only LOW proof → Proof-First abstention, no invented move.
    report = run_scan("niche", [_cand("hype", STRONG, ProofLevel.LOW, sourced=False)])
    assert report.daily_move is None
    assert report.abstained_reason is not None
    assert "proof" in report.abstained_reason.lower()


def test_abstains_when_nothing_buildable() -> None:
    report = run_scan("niche", [_cand("meh", WEAK, ProofLevel.HIGH)])
    assert report.daily_move is None
    assert "threshold" in (report.abstained_reason or "")


def test_hard_gate_keeps_move_out_even_with_proof() -> None:
    gated = _cand("scrapey", STRONG, ProofLevel.HIGH, gates=HardGates(legally_gray_or_pii=True))
    report = run_scan("niche", [gated])
    assert report.daily_move is None  # gate forced ARCHIVE → not eligible
    assert report.shortlist[0].band == Band.ARCHIVE


def test_unscorable_candidate_dropped_not_guessed() -> None:
    no_factors = OpportunityCandidate(name="?", summary="x", factors=None)
    report = run_scan("niche", [no_factors, _cand("strong", STRONG, ProofLevel.HIGH)])
    assert [s.candidate.name for s in report.shortlist] == ["strong"]
