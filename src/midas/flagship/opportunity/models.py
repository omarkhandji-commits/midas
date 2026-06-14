"""Proof-First revenue artifacts.

The flagship loop is Discover → Prove → Score → Prepare → Estimate → Approve → Track.
These models carry the *evidence* through every stage:

- An `OpportunityCandidate` must carry sourced `Finding`s (Prove) before it can score.
- A `ScenarioEstimate` is an *estimate* with explicit assumptions and a proof level —
  never a prediction. We measure cost precisely (receipts); revenue is user-confirmed.
- The `DailyRevenueMove` is the single headline artifact: one prepared move that stops
  *before* any risky/outbound action (approval-default).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from midas.core.agents.summary import Finding, ProofLevel
from midas.flagship.scoring import Band, FactorScores, HardGates, ScoreBreakdown


@dataclass
class OpportunityCandidate:
    """A discovered opportunity with its evidence and scoring inputs."""

    name: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    factors: FactorScores | None = None
    gates: HardGates = field(default_factory=HardGates)

    @property
    def proof_level(self) -> ProofLevel:
        if not self.findings:
            return ProofLevel.LOW
        return min((f.proof_level for f in self.findings), key=lambda p: p.rank)

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for f in self.findings:
            for s in f.sources:
                if s not in seen:
                    seen.append(s)
        return seen


@dataclass
class ScoredCandidate:
    candidate: OpportunityCandidate
    breakdown: ScoreBreakdown

    @property
    def band(self) -> Band:
        return self.breakdown.band


@dataclass
class ScenarioEstimate:
    """A labeled estimate — assumptions explicit, proof level attached. NOT a prediction."""

    assumptions: list[str]
    est_cost_usd: float  # what it would cost to attempt (best-effort)
    est_time_hours: float
    proof_level: ProofLevel = ProofLevel.LOW
    note: str = "Estimate, not a prediction. No revenue is promised."


@dataclass
class BuildBrief:
    """Prepared assets/plan for the move. Drafts only — nothing is executed."""

    steps: list[str]
    draft_assets: dict[str, str] = field(default_factory=dict)  # e.g. {"landing_copy": "..."}


@dataclass
class DailyRevenueMove:
    """The single headline output. Prepared and proven, then it WAITS for approval."""

    candidate: OpportunityCandidate
    breakdown: ScoreBreakdown
    brief: BuildBrief
    estimate: ScenarioEstimate
    # The next action that would actually earn — deliberately NOT executed here.
    next_action: str
    next_action_requires_approval: bool = True

    @property
    def proof_level(self) -> ProofLevel:
        return self.candidate.proof_level


@dataclass
class ScanReport:
    niche: str
    shortlist: list[ScoredCandidate]
    daily_move: DailyRevenueMove | None
    spent_usd: float
    abstained_reason: str | None = None  # set when no move met the proof bar

    @property
    def proof_level(self) -> ProofLevel:
        if self.daily_move is None:
            return ProofLevel.LOW
        return self.daily_move.proof_level
