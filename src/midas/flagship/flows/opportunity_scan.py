"""The V1 demo flow: scan a niche → a proven, prepared Daily Revenue Move.

Implements the Proof-First loop end to end on already-discovered candidates:
    Score → (select, proof-gated) → Prepare → Estimate → stop before Approve.

It STOPS before any outbound/irreversible action — the move is handed to the human
(approval-default). Cost is read precisely from the receipts ledger; no revenue is
ever promised or predicted.
"""

from __future__ import annotations

from collections.abc import Callable

from midas.core.agents.summary import ProofLevel
from midas.flagship.opportunity.models import (
    BuildBrief,
    DailyRevenueMove,
    OpportunityCandidate,
    ScanReport,
    ScenarioEstimate,
    ScoredCandidate,
)
from midas.flagship.scoring import Band, score

# Minimum evidence a candidate needs before it can be the headline move. Matches
# policy.sources.min_confidence_for_action (default MEDIUM): we'd rather abstain than
# put an unsourced move in front of the operator.
DEFAULT_MIN_PROOF = ProofLevel.MEDIUM

PrepareFn = Callable[[OpportunityCandidate], BuildBrief]
EstimateFn = Callable[[OpportunityCandidate], ScenarioEstimate]


def _default_brief(c: OpportunityCandidate) -> BuildBrief:
    # Use heuristic drafts so the brief always carries real assets — even offline,
    # the operator gets an offer/landing/email/SEO/script to edit. The LLM-backed
    # path is opt-in via prepare_fn injection (see `run_scan(prepare_fn=...)`).
    from midas.flagship.assets import heuristic_assets

    assets = heuristic_assets(c)
    return BuildBrief(
        steps=[
            f"Validate the pain '{c.name}' against its sources before spending.",
            "Review the drafted offer/landing/email — edit before any send.",
            "Pick ONE asset to ship first; the others stay as drafts.",
        ],
        draft_assets=assets.as_dict(),
    )


def _default_estimate(c: OpportunityCandidate) -> ScenarioEstimate:
    return ScenarioEstimate(
        assumptions=[
            "Operator spends <2h preparing the offer.",
            "Distribution uses an existing free channel.",
            "No paid ads in the first attempt.",
        ],
        est_cost_usd=0.0,
        est_time_hours=2.0,
        proof_level=c.proof_level,
    )


def run_scan(
    niche: str,
    candidates: list[OpportunityCandidate],
    *,
    ledger: object | None = None,
    memory: object | None = None,
    min_proof: ProofLevel = DEFAULT_MIN_PROOF,
    prepare_fn: PrepareFn = _default_brief,
    estimate_fn: EstimateFn = _default_estimate,
) -> ScanReport:
    # Score stage — every candidate gets a transparent /100 breakdown.
    scored: list[ScoredCandidate] = []
    for c in candidates:
        if c.factors is None:
            continue  # cannot score without factor inputs — drop rather than guess
        scored.append(ScoredCandidate(c, score(c.factors, c.gates)))

    shortlist = sorted(scored, key=lambda s: s.breakdown.total, reverse=True)

    # Select the Daily Revenue Move: highest-scoring candidate that is buildable AND
    # meets the proof bar. Otherwise abstain — never invent a move.
    daily_move: DailyRevenueMove | None = None
    abstained: str | None = None
    eligible = [s for s in shortlist if s.band in (Band.BUILD, Band.WATCHLIST)]
    proven = [s for s in eligible if s.candidate.proof_level.rank >= min_proof.rank]

    if not eligible:
        abstained = "no candidate scored above the watchlist threshold"
    elif not proven:
        abstained = (
            f"top candidates lacked {min_proof.value}+ proof "
            f"(Proof-First: abstaining rather than presenting an unsourced move)"
        )
    else:
        top = proven[0]
        c = top.candidate
        daily_move = DailyRevenueMove(
            candidate=c,
            breakdown=top.breakdown,
            brief=prepare_fn(c),
            estimate=estimate_fn(c),
            next_action=f"Launch the prepared offer for '{c.name}'",
            next_action_requires_approval=True,
        )

    # Close the loop: log what the scan decided (or why it abstained) into memory.
    # Future scans will see this via context_pack() and avoid re-proposing the same move.
    if memory is not None:
        _log_scan_decision(memory, niche, daily_move, abstained, shortlist)

    spent = _spent_from_ledger(ledger)
    return ScanReport(
        niche=niche,
        shortlist=shortlist,
        daily_move=daily_move,
        spent_usd=spent,
        abstained_reason=abstained,
    )


def scan_niche(
    niche: str,
    *,
    router: object,
    search: object | None = None,
    verifier: object | None = None,
    ledger: object | None = None,
    memory: object | None = None,
    min_proof: ProofLevel = DEFAULT_MIN_PROOF,
    run_id: str | None = None,
    task_id: str | None = None,
    est_usd: float = 0.0,
) -> ScanReport:
    """Full Proof-First flow: Discover (search-grounded + source-verified) → Score →
    select → Prepare/Estimate.

    The router call is budgeted + receipted; cost in the report is read back from the
    ledger. Stops before any outbound action (approval-default).
    """
    from .discover import discover_candidates

    candidates = discover_candidates(
        niche,
        router=router,  # type: ignore[arg-type]
        search=search,  # type: ignore[arg-type]
        verifier=verifier,  # type: ignore[arg-type]
        run_id=run_id,
        task_id=task_id,
        est_usd=est_usd,
    )
    return run_scan(niche, candidates, ledger=ledger, memory=memory, min_proof=min_proof)


def _log_scan_decision(
    memory: object,
    niche: str,
    move: DailyRevenueMove | None,
    abstained: str | None,
    shortlist: list[ScoredCandidate],
) -> None:
    """Write the scan's decision into memory's DECISION namespace (Proof-First sourcing)."""
    from midas.core.memory import MemoryKind  # local import: avoid circular at module load

    try:
        record = getattr(memory, "record_decision")
    except AttributeError:
        return
    rejected = [s.candidate.name for s in shortlist[1:4]]  # top alternates we passed on
    if move is not None:
        record(
            f"scan:{niche}",
            chose=move.candidate.name,
            rejected=rejected,
            why=(f"top-scored ({move.breakdown.total:.1f}) and proven "
                 f"({move.proof_level.value})"),
            sources=move.candidate.sources,
        )
    else:
        getattr(memory, "remember")(
            MemoryKind.DECISION,
            f"scan:{niche}",
            f"abstained: {abstained}",
        )


def _spent_from_ledger(ledger: object | None) -> float:
    if ledger is None:
        return 0.0
    try:
        return round(sum(r.body.cost_usd for r in ledger), 6)  # type: ignore[attr-defined]
    except TypeError:
        return 0.0
