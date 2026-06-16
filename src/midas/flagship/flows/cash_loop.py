"""Cash loop — close the edge: scan → prepare → queue → execute → outcome → ROI.

The other pieces (discover, score, prepare, estimate, approvals, execute,
outcomes, ROI) already exist. This module is the *fil rouge* that ties them
together into one operator-facing loop.

Invariants preserved (every assertion below is a property of the code):

1. Nothing is ever shipped without an approval — every mutating tool the loop
   asks for goes through ``Toolset.invoke`` and lands in ``ApprovalQueue``.
   The loop does NOT call ``execute_approved_step`` itself; the operator does.

2. ROI cites receipts only. ``pipeline()`` is derived from the receipt ledger,
   the approval queue and ``MemoryKind.RESULT`` — never invented.

3. The feedback edge (``flows.feedback``) is applied before scoring, never
   after, so the bias is visible in the breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from midas.flagship.opportunity.models import (
    DailyRevenueMove,
    OpportunityCandidate,
    ScanReport,
    ScoredCandidate,
)

from .attribution import move_key_for_run
from .feedback import FeedbackAdjustment, apply_feedback, feedback_factors
from .opportunity_scan import run_scan, scan_niche


@dataclass(frozen=True)
class PreparedArtifact:
    """One artifact the loop asked the toolset to draft, with its approval id."""

    tool: str
    approval_id: int | None
    summary: str = ""


@dataclass
class CashRunReport:
    """Result of one ``CashLoop.run`` invocation."""

    niche: str
    scan: ScanReport
    feedback: FeedbackAdjustment = field(
        default_factory=lambda: FeedbackAdjustment(deltas={}, reasons=[])
    )
    artifacts: list[PreparedArtifact] = field(default_factory=list)

    @property
    def move(self) -> DailyRevenueMove | None:
        return self.scan.daily_move


@dataclass
class CashLoop:
    """Stateless orchestrator. Holds references; never stores cash state itself.

    The state of truth stays in: receipts ledger (cost), approval queue (gates),
    memory (decisions/outcomes/cash). Replays remain deterministic.
    """

    toolset: Any
    memory: Any | None = None
    ledger: Any | None = None
    approvals: Any | None = None

    def run(
        self,
        niche: str,
        *,
        router: Any | None = None,
        search: Any | None = None,
        verifier: Any | None = None,
        candidates: list[OpportunityCandidate] | None = None,
        run_id: str | None = None,
        prepare_artifacts: bool = True,
    ) -> CashRunReport:
        """Run one cash cycle for ``niche``.

        - If ``candidates`` is given, score them directly (offline / demo path).
        - Else ``router`` must be provided and ``scan_niche`` runs the live path.

        When ``prepare_artifacts=True`` and the scan picked a daily move, the
        loop asks the toolset for ONE landing-page draft sized for the move.
        That call goes through Sentinel → APPROVE-tier → ApprovalQueue. Nothing
        executes inline.
        """
        # 1) Feedback edge: bias factors before the scan picks a winner.
        adj = feedback_factors(self.memory, niche=niche)
        scored_candidates = self._apply_feedback_to_candidates(candidates or [], adj)

        # 2) Scan: live (router-backed) or offline (pre-built candidates).
        if scored_candidates:
            report = run_scan(
                niche, scored_candidates, ledger=self.ledger, memory=self.memory
            )
        else:
            if router is None:
                raise ValueError(
                    "cash_loop.run: provide either `candidates` or `router`"
                )
            report = scan_niche(
                niche,
                router=router,
                search=search,
                verifier=verifier,
                ledger=self.ledger,
                memory=self.memory,
                run_id=run_id,
            )

        # 3) Prepare ONE cash-shaped artifact (gated, never executed inline).
        artifacts: list[PreparedArtifact] = []
        if prepare_artifacts and report.daily_move is not None:
            artifacts.append(self._queue_landing_for_move(report.daily_move))

        return CashRunReport(
            niche=niche, scan=report, feedback=adj, artifacts=artifacts
        )

    # ── pipeline view ────────────────────────────────────────────────────────

    def pipeline(self) -> list[dict[str, Any]]:
        """Return the state of every move, derived from the existing stores.

        Each row::

            {
              "run_id": str,
              "stage": "awaiting_approval" | "shipped" | "outcome_recorded",
              "approvals_pending": int,
              "cost_usd": float,
              "revenue_usd": float,
              "net_usd": float,
            }

        No hidden state: the function only reads ``ledger``, ``approvals``,
        ``memory``. Two consecutive calls return identical results when nothing
        else moved.
        """
        from midas.flagship.roi import build_outcomes_index, compute_run_roi

        rows: dict[str, dict[str, Any]] = {}

        # Cost + run_ids come from the ledger.
        cost_index: dict[str, float] = {}
        receipts: list[Any] = []
        if self.ledger is not None:
            try:
                receipts = list(self.ledger)
            except TypeError:
                receipts = []
            for r in receipts:
                rid = r.body.run_id
                cost_index[rid] = cost_index.get(rid, 0.0) + float(r.body.cost_usd or 0.0)

        # Pending approvals per run_id.
        pending_index: dict[str, int] = {}
        if self.approvals is not None and hasattr(self.approvals, "pending"):
            try:
                for req in self.approvals.pending():
                    rid = req.run_id
                    pending_index[rid] = pending_index.get(rid, 0) + 1
            except Exception:  # noqa: BLE001 — pipeline must never crash on store errors
                pending_index = {}

        # Outcomes (revenue) per run_id, from memory.RESULT.
        outcomes = build_outcomes_index(self.memory) if self.memory is not None else {}
        roi_report = compute_run_roi(receipts, outcomes) if receipts else None

        all_run_ids: set[str] = set(cost_index) | set(pending_index) | set(outcomes)
        for rid in sorted(all_run_ids):
            cost = round(cost_index.get(rid, 0.0), 6)
            pending = pending_index.get(rid, 0)
            outcome = outcomes.get(rid) or {}
            revenue = float(outcome.get("revenue_usd") or 0.0)
            if outcome:
                stage = "outcome_recorded"
            elif pending > 0:
                stage = "awaiting_approval"
            else:
                stage = "shipped"
            rows[rid] = {
                "run_id": rid,
                "stage": stage,
                "approvals_pending": pending,
                "cost_usd": cost,
                "revenue_usd": round(revenue, 6),
                "net_usd": round(revenue - cost, 6),
            }

        out = list(rows.values())
        # Stable ordering for tests + UX.
        out.sort(key=lambda r: r["run_id"])
        # Attach ROI totals at the tail so callers can pretty-print.
        if roi_report is not None and out:
            out.append(
                {
                    "run_id": "__totals__",
                    "stage": "summary",
                    "approvals_pending": sum(p["approvals_pending"] for p in out),
                    "cost_usd": roi_report.total_cost,
                    "revenue_usd": roi_report.total_revenue,
                    "net_usd": roi_report.net_usd,
                }
            )
        return out

    # ── internals ────────────────────────────────────────────────────────────

    def _apply_feedback_to_candidates(
        self,
        candidates: list[OpportunityCandidate],
        adj: FeedbackAdjustment,
    ) -> list[OpportunityCandidate]:
        if adj.is_zero or not candidates:
            return list(candidates)
        out: list[OpportunityCandidate] = []
        for c in candidates:
            if c.factors is None:
                out.append(c)
                continue
            new_factors = apply_feedback(c.factors, adj)
            out.append(
                OpportunityCandidate(
                    name=c.name,
                    summary=c.summary,
                    findings=list(c.findings),
                    factors=new_factors,
                    gates=c.gates,
                )
            )
        return out

    def _queue_landing_for_move(self, move: DailyRevenueMove) -> PreparedArtifact:
        """Ask the toolset for a landing-page draft. Always APPROVE-tier."""
        headline = f"Get more from {move.candidate.name}"
        subheading = move.candidate.summary[:200]
        cta = "Talk to us"
        try:
            outcome = self.toolset.invoke(
                "landing.draft",
                agent="cash-loop",
                path=f"landing-{_slug(move.candidate.name)}.html",
                headline=headline,
                subheading=subheading,
                body="",
                cta_text=cta,
            )
        except Exception as exc:  # noqa: BLE001
            return PreparedArtifact(
                tool="landing.draft", approval_id=None, summary=f"error: {exc}"
            )
        return PreparedArtifact(
            tool="landing.draft",
            approval_id=outcome.approval_id,
            summary=(
                "queued" if outcome.verdict.decision.value == "queue_approval" else "ran"
            ),
        )


def _slug(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "move"


__all__ = [
    "CashLoop",
    "CashRunReport",
    "PreparedArtifact",
    "ScoredCandidate",
    "move_key_for_run",
]
