"""Outcome ingestion — what actually happened after the operator approved a move.

Closes the Track loop in `Discover → Prove → Score → Prepare → Estimate → Approve → Track`.
The operator (or a wired analytics adapter later) reports real numbers: replies, clicks,
sales, errors. We persist them as RESULT memory (Proof-First: sourced if a metric URL is
provided) and write a receipt so the audit chain stays whole.

Honesty rules baked in:
- we record what the operator reports, period — we don't infer revenue or attribute it;
- a metric without a source defaults to LOW proof, never MEDIUM/HIGH;
- comparing outcome to estimate is descriptive ("est vs actual"), never predictive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from midas.core.agents.summary import ProofLevel
from midas.core.memory import MemoryEntry, MemoryKind


@dataclass(frozen=True)
class Outcome:
    """One observed result tied to a previously-approved move."""

    move_key: str  # e.g. the candidate name or run id the operator wants to track under
    outcome: str  # human-readable summary
    metrics: dict[str, float] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)  # links to analytics, CRM, etc.
    note: str = ""


def ingest_outcome(
    outcome: Outcome,
    *,
    memory: Any,
    ledger: Any = None,
    run_id: str = "",
) -> MemoryEntry:
    """Persist the outcome as RESULT memory (+ optional receipt for the audit chain).

    Returns the written memory entry so callers can echo it back to the operator.
    """
    if not outcome.move_key.strip():
        raise ValueError("move_key must be a non-empty identifier")

    entry: MemoryEntry = memory.record_result(
        outcome.move_key,
        outcome=outcome.outcome,
        metrics=outcome.metrics or None,
        sources=outcome.sources or None,
    )

    if ledger is not None:
        from midas.core.receipts.models import Decision

        # The receipt captures only the SHAPE of what was logged — not raw PII —
        # so the audit trail stays useful without leaking the operator's data.
        ledger.append(
            run_id=run_id,
            agent="outcomes",
            tool="record_result",
            decision=Decision.ALLOW,
            inputs={"move_key": outcome.move_key, "metric_keys": sorted(outcome.metrics)},
            outputs={
                "proof_level": entry.proof_level.value,
                "sourced": bool(outcome.sources),
            },
        )
    return entry


def summarize_history(memory: Any, move_key: str) -> dict[str, Any]:
    """Compact summary the dashboard can render. Live values only, oldest→newest."""
    rows = [r for r in memory.history(MemoryKind.RESULT, move_key) if not r.superseded]
    return {
        "move_key": move_key,
        "count": len(rows),
        "latest": rows[-1].content if rows else None,
        "proof": (rows[-1].proof_level.value if rows else ProofLevel.LOW.value),
        "sources": (rows[-1].sources if rows else []),
    }
