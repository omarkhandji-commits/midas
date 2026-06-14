"""Bundled demo data so `midas scan` produces a real Daily Revenue Move with zero
API keys configured. These candidates are illustrative and clearly sourced — the
point is to show the Proof-First output shape, not to recommend a real venture.
"""

from __future__ import annotations

from midas.core.agents.summary import Finding, ProofLevel
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores, HardGates


def demo_candidates() -> list[OpportunityCandidate]:
    return [
        OpportunityCandidate(
            name="Invoice-chasing assistant for solo trades",
            summary="A tiny tool that drafts polite late-invoice follow-ups for trades.",
            findings=[
                Finding(
                    "Solo tradespeople repeatedly complain about unpaid invoices and chasing.",
                    ProofLevel.HIGH,
                    sources=["reddit.com/r/Plumbing", "reddit.com/r/Electricians"],
                ),
                Finding(
                    "Existing tools are heavy accounting suites; a focused helper is a gap.",
                    ProofLevel.MEDIUM,
                    sources=["news.ycombinator.com/item-demo"],
                ),
            ],
            factors=FactorScores(
                demand=8, speed_to_cash=8, mrr_potential=8, low_support=7, defensibility=5,
                low_competition=6, distribution=7, low_cost=9, low_launch_time=8, low_risk=8,
                operator_fit=7,
            ),
            gates=HardGates(),
        ),
        OpportunityCandidate(
            name="Generic 'AI newsletter' aggregator",
            summary="Yet another auto-generated AI-news roundup.",
            findings=[
                Finding(
                    "Inferred interest; no concrete sourced pain.",
                    ProofLevel.LOW,
                ),
            ],
            factors=FactorScores(
                demand=5, speed_to_cash=6, mrr_potential=4, low_support=6, defensibility=2,
                low_competition=2, distribution=4, low_cost=8, low_launch_time=7, low_risk=6,
                operator_fit=5,
            ),
            gates=HardGates(),
        ),
    ]
