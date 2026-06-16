"""Cash heartbeat — autonomous in **preparation** only.

What this does. Runs the cash loop across multiple niches in one pass, preparing
moves and queuing approvals. While the operator sleeps, MIDAS works on the
*prepare* side and **stacks signed approvals** waiting for one tap.

What this NEVER does. Execute. Ship. Send. Spend. Auto-approve. Every tool call
still goes through ``Toolset.invoke → Sentinel → ApprovalQueue``. The heartbeat
adds zero new write paths.

Guardrails (reused, not reinvented):

- :class:`midas.core.budget.fuse.BudgetFuse` — atomic per-task/daily/monthly caps,
  enforced by the router on every LLM call. Heartbeat doesn't bypass it.
- :class:`midas.core.budget.loop_breaker.LoopBreaker` — wall-clock, iteration and
  no-progress caps. Used here to bound an autonomous batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from .cash_loop import CashLoop, CashRunReport


@dataclass
class HeartbeatReport:
    """Aggregate of one heartbeat pass."""

    niches: list[str]
    runs: list[CashRunReport] = field(default_factory=list)
    approvals_queued: int = 0
    elapsed_seconds: float = 0.0
    stopped_reason: str = ""

    @property
    def queued_per_niche(self) -> dict[str, int]:
        return {r.niche: len(r.artifacts) for r in self.runs}


@dataclass
class CashHeartbeat:
    """Bounded autonomous preparation pass.

    No daemon, no hidden thread — the operator (or `midas schedule recipe`) is
    responsible for invoking ``run_once`` on the cadence they want. That keeps
    the surface auditable: one heartbeat == one explicit invocation.
    """

    loop: CashLoop
    router: Any | None = None
    search: Any | None = None
    verifier: Any | None = None
    # Hard caps — the heartbeat MUST stop, even if niches remain.
    max_niches: int = 10
    max_seconds: float = 600.0  # 10 minutes default
    max_artifacts: int = 20

    def run_once(
        self,
        niches: list[str],
        *,
        live: bool = False,
        candidates_by_niche: dict[str, list[Any]] | None = None,
    ) -> HeartbeatReport:
        """Run ONE preparation pass across ``niches``. Stops on any cap.

        - ``live=False`` (default): each niche must have an entry in
          ``candidates_by_niche`` (offline / demo path). Useful for tests and
          for users without an LLM configured.
        - ``live=True``: requires ``self.router`` to be set; falls through to
          :meth:`CashLoop.run` with the router/search/verifier.
        """
        report = HeartbeatReport(niches=list(niches))
        if not niches:
            report.stopped_reason = "no niches"
            return report

        candidates_by_niche = candidates_by_niche or {}
        t0 = monotonic()
        for niche in niches[: self.max_niches]:
            elapsed = monotonic() - t0
            if elapsed >= self.max_seconds:
                report.stopped_reason = f"max_seconds={self.max_seconds:.0f}s"
                break
            if report.approvals_queued >= self.max_artifacts:
                report.stopped_reason = f"max_artifacts={self.max_artifacts}"
                break

            try:
                if live:
                    if self.router is None:
                        report.stopped_reason = "live=True but no router configured"
                        break
                    run = self.loop.run(
                        niche,
                        router=self.router,
                        search=self.search,
                        verifier=self.verifier,
                        run_id=f"heartbeat:{niche}",
                    )
                else:
                    cands = candidates_by_niche.get(niche, [])
                    if not cands:
                        # Skip — without offline candidates and without live router,
                        # there's nothing we can prepare honestly. Don't fabricate.
                        continue
                    run = self.loop.run(niche, candidates=cands)
            except Exception as exc:  # noqa: BLE001 — never crash a heartbeat
                report.stopped_reason = f"error on {niche!r}: {exc}"
                break

            report.runs.append(run)
            report.approvals_queued += sum(
                1 for a in run.artifacts if a.approval_id is not None
            )
        else:
            # Loop completed naturally (no break).
            if not report.stopped_reason:
                report.stopped_reason = "completed"

        report.elapsed_seconds = round(monotonic() - t0, 3)
        return report


__all__ = ["CashHeartbeat", "HeartbeatReport"]
