"""Concise, structured results that subagents return to the supervisor.

Isolated subagents NEVER leak raw chatter back to the supervisor — they return a
`SubagentResult` (a bounded summary). This keeps the supervisor's context small
(no O(n^2) blow-up) and forces every claim to carry its evidence.

Proof-First contract: every finding carries a ProofLevel and its sources. A claim
that cannot be sourced is omitted, never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ProofLevel(StrEnum):
    """How well-evidenced a claim is. Shown on every finding (Proof-First)."""

    HIGH = "high"  # multiple independent, citable sources
    MEDIUM = "medium"  # a single credible source, or strong indirect signal
    LOW = "low"  # weak / inferred — surfaced as such, never as fact

    @property
    def rank(self) -> int:
        return {"high": 3, "medium": 2, "low": 1}[self.value]


@dataclass
class Finding:
    """One evidenced claim. `sources` are URLs/identifiers backing it."""

    claim: str
    proof_level: ProofLevel
    sources: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Proof-First: a HIGH/MEDIUM claim must cite at least one source.
        if self.proof_level.rank >= ProofLevel.MEDIUM.rank and not self.sources:
            raise ValueError(
                f"finding claims proof_level={self.proof_level.value} but has no sources"
            )


@dataclass
class SubagentResult:
    """The bounded summary a subagent hands back. No raw transcript."""

    role: str
    findings: list[Finding] = field(default_factory=list)
    notes: str = ""
    cost_usd: float = 0.0
    tokens: int = 0
    escalated: bool = False  # subagent flagged low confidence → wants human/council

    @property
    def proof_level(self) -> ProofLevel:
        """The result is only as strong as its weakest *load-bearing* finding."""
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
