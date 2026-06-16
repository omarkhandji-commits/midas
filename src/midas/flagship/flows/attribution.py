"""Attribution helpers — link outcomes to their originating run.

The ROI ledger joins receipted cost (from `receipts.jsonl`) with operator-recorded
revenue (from RESULT memories) by ``run_id``. For the join to actually fire, the
outcome's `move_key` must equal the scan's `run_id`. This helper standardizes the
key so future scans don't end up with orphaned outcomes.

Nothing here invents revenue. We only build a key string and a small wrapper
around ``memory.record_result`` that *uses the run_id as the move_key*.
"""

from __future__ import annotations

from typing import Any


def move_key_for_run(run_id: str) -> str:
    """Canonical move_key for a given scan run.

    Keep it identical to the run_id so :func:`midas.flagship.roi.compute_run_roi`
    joins cost ↔ revenue cleanly. We pass it through ``str`` only to defend
    against accidental ints/None reaching the memory writer.
    """
    if not run_id:
        raise ValueError("attribution: run_id is required to link an outcome")
    return str(run_id)


def link_outcome_to_run(
    memory: Any,
    *,
    run_id: str,
    outcome: str,
    metrics: dict[str, float] | None = None,
    sources: list[str] | None = None,
) -> Any:
    """Record an outcome whose ``move_key == run_id``.

    Returns the new MemoryEntry. Proof-First: ``record_result`` already promotes
    proof_level to MEDIUM only when sources are provided. ``revenue`` (if any) is
    expected as a metric key — that's the contract ``build_outcomes_index`` reads.
    """
    if not hasattr(memory, "record_result"):
        raise TypeError("memory store does not expose record_result")
    return memory.record_result(
        move_key_for_run(run_id),
        outcome=outcome,
        metrics=metrics or {},
        sources=sources or [],
    )
