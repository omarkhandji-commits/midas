"""Provable ROI ledger — ties run cost (from receipts) to recorded outcomes.

Every figure traces back to a signed receipt and a recorded outcome. Nothing here
projects revenue or claims a number that isn't already in the chain — Proof-First
applies. Outcomes are recorded by the operator via ``midas outcome record`` and
land in ``MemoryStore`` under :class:`MemoryKind.RESULT` (see ``flagship/outcomes.py``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunRoi:
    run_id: str
    cost_usd: float
    revenue_usd: float
    sources: list[str] = field(default_factory=list)
    receipt_count: int = 0

    @property
    def net_usd(self) -> float:
        return round(self.revenue_usd - self.cost_usd, 6)

    @property
    def roi_ratio(self) -> float | None:
        if self.cost_usd <= 0:
            return None
        return round(self.revenue_usd / self.cost_usd, 4)


@dataclass
class RoiReport:
    runs: list[RunRoi] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return round(sum(r.cost_usd for r in self.runs), 6)

    @property
    def total_revenue(self) -> float:
        return round(sum(r.revenue_usd for r in self.runs), 6)

    @property
    def net_usd(self) -> float:
        return round(self.total_revenue - self.total_cost, 6)


def compute_run_roi(
    receipts: Iterable[Any],
    outcomes: dict[str, dict[str, Any]],
) -> RoiReport:
    """Group receipts by ``run_id`` and join with operator-recorded outcomes.

    Parameters
    ----------
    receipts:
        Any iterable yielding :class:`Receipt` objects (``ledger`` is one).
    outcomes:
        ``{run_id: {"revenue_usd": float, "sources": [str, ...]}}``. Built from
        :func:`build_outcomes_index` against the operator's ``MemoryStore``.

    Only runs that have at least one receipt are included. A run with no recorded
    outcome shows ``revenue_usd=0`` (and no ROI ratio) — never an invented number.
    """
    by_run: dict[str, list[Any]] = defaultdict(list)
    for receipt in receipts:
        by_run[receipt.body.run_id].append(receipt)
    out = RoiReport()
    for run_id, receipts_for_run in by_run.items():
        cost = round(sum(r.body.cost_usd for r in receipts_for_run), 6)
        outcome = outcomes.get(run_id) or {}
        revenue = float(outcome.get("revenue_usd") or 0.0)
        sources = [str(s) for s in (outcome.get("sources") or [])]
        out.runs.append(
            RunRoi(
                run_id=run_id,
                cost_usd=cost,
                revenue_usd=round(revenue, 6),
                sources=sources,
                receipt_count=len(receipts_for_run),
            )
        )
    out.runs.sort(key=lambda r: r.run_id)
    return out


def build_outcomes_index(memory: Any) -> dict[str, dict[str, Any]]:
    """Walk RESULT memories and pull a ``{run_id: {revenue, sources}}`` index.

    Convention: outcomes recorded via ``midas outcome record --move-key <run_id>``
    are stored in memory with ``key=<run_id>`` and (optionally) a ``revenue=<n>``
    metric in the content string. ``MemoryStore.recall`` returns newest-first; the
    most recent supersedes earlier values.
    """
    from midas.core.memory import MemoryKind

    if memory is None or not hasattr(memory, "recall"):
        return {}
    seen: set[str] = set()
    index: dict[str, dict[str, Any]] = {}
    for entry in memory.recall(kind=MemoryKind.RESULT, limit=500):
        if entry.key in seen:
            continue
        seen.add(entry.key)
        revenue = _extract_metric(entry.content, "revenue")
        index[entry.key] = {
            "revenue_usd": revenue or 0.0,
            "sources": list(entry.sources),
        }
    return index


def _extract_metric(content: str, name: str) -> float | None:
    """Pull `name=<number>` out of the metrics suffix written by ``record_result``."""
    import re

    match = re.search(rf"{re.escape(name)}\s*=\s*(-?[0-9]+(?:\.[0-9]+)?)", content)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def format_roi_report(report: RoiReport) -> str:
    """Compact table for CLI output. Avoids markdown so the terminal stays readable."""
    if not report.runs:
        return "No runs yet."
    rows: list[str] = []
    rows.append(
        f"{'run_id':<36} {'cost':>10} {'rev':>10} {'net':>10}"
        f" {'roi':>8} {'rcpts':>6}"
    )
    rows.append("-" * 84)
    for r in report.runs:
        roi = f"{r.roi_ratio:.2f}x" if r.roi_ratio is not None else "—"
        rows.append(
            f"{r.run_id[:36]:<36} {r.cost_usd:>10.4f} {r.revenue_usd:>10.2f}"
            f" {r.net_usd:>10.2f} {roi:>8} {r.receipt_count:>6}"
        )
    rows.append("-" * 84)
    rows.append(
        f"{'TOTAL':<36} {report.total_cost:>10.4f} {report.total_revenue:>10.2f}"
        f" {report.net_usd:>10.2f}"
    )
    rows.append("")
    rows.append(
        "Every figure traces back to a signed receipt (cost) and a recorded outcome "
        "(revenue). No projections."
    )
    return "\n".join(rows)
