"""Supervisor — the single orchestrator.

One supervisor dispatches isolated subagents and collects their bounded summaries.
There is no peer-to-peer chatter between subagents (avoids O(n^2) context growth and
the fragility of free-form multi-agent swarms). Every dispatched step ticks the
loop-breaker with a canonical state hash, so a stuck or non-progressing run is killed
by spend, wall-clock, iterations, OR lack of progress.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from midas.core.budget.loop_breaker import LoopBreaker

from .subagent import Subagent
from .summary import ProofLevel, SubagentResult


@dataclass
class DispatchResult:
    """What the supervisor gathered from a fan-out of subagents."""

    results: list[SubagentResult] = field(default_factory=list)
    stopped_reason: str | None = None  # set if the loop-breaker tripped mid-run

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.results)

    @property
    def escalations(self) -> list[SubagentResult]:
        return [r for r in self.results if r.escalated]

    @property
    def overall_proof_level(self) -> ProofLevel:
        """The fan-out is only as trustworthy as its weakest contributing result."""
        if not self.results:
            return ProofLevel.LOW
        return min((r.proof_level for r in self.results), key=lambda p: p.rank)


@dataclass
class _Job:
    agent: Subagent
    task: str
    context: str = ""
    est_usd: float = 0.0


class Supervisor:
    def __init__(self, *, loop_breaker: LoopBreaker | None = None, run_id: str = "") -> None:
        self._breaker = loop_breaker or LoopBreaker()
        self._run_id = run_id
        self._jobs: list[_Job] = []

    def add(self, agent: Subagent, task: str, *, context: str = "", est_usd: float = 0.0) -> None:
        self._jobs.append(_Job(agent, task, context, est_usd))

    def dispatch(self, *, task_id: str | None = None) -> DispatchResult:
        out = DispatchResult()
        for job in self._jobs:
            # state hash = roles already completed + which job we're on → trips the
            # no-progress detector if a job silently fails to advance the run.
            state = {"done": [r.role for r in out.results], "next": job.agent.role}
            try:
                self._breaker.tick(state=state, tokens=0)
            except Exception as exc:  # LoopBroken
                out.stopped_reason = getattr(exc, "reason", str(exc))
                break

            result = job.agent.run(
                job.task,
                context=job.context,
                run_id=self._run_id,
                task_id=task_id,
                est_usd=job.est_usd,
            )
            out.results.append(result)
            # Account the tokens this job spent; a runaway token total trips here.
            try:
                self._breaker.tick(
                    state={"completed": result.role}, tokens=result.tokens
                )
            except Exception as exc:  # LoopBroken
                out.stopped_reason = getattr(exc, "reason", str(exc))
                break
        return out
