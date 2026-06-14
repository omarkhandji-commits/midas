"""Isolated subagent — a single-purpose worker the supervisor dispatches.

Each subagent gets its own role, its own slice of context, and a token budget. It
runs its task against the (budgeted, receipted) router and returns a `SubagentResult`
summary — never raw transcript. Lesson from production multi-agent systems: keep
workers isolated and make them return bounded summaries, or context explodes and the
system becomes fragile.

The parser that turns model text into evidenced `Finding`s is injected, so tests run
fully offline (fake router + fake parser) and so flagship subagents can enforce their
own Proof-First sourcing rules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from midas.core.router.router import LLMRouter

from .summary import Finding, ProofLevel, SubagentResult

# A parser turns the model's raw text into evidenced findings. Returning [] means the
# worker found nothing it could source — the result is then flagged for escalation.
Parser = Callable[[str], list[Finding]]


class Subagent:
    def __init__(
        self,
        role: str,
        *,
        router: LLMRouter,
        parser: Parser,
        system: str = "",
        model_role: str = "cheap",
        escalate: bool = False,
    ) -> None:
        self.role = role
        self._router = router
        self._parser = parser
        self._system = system
        self._model_role = model_role
        self._escalate = escalate

    def run(
        self,
        task: str,
        *,
        context: str = "",
        run_id: str | None = None,
        task_id: str | None = None,
        est_usd: float = 0.0,
    ) -> SubagentResult:
        messages: list[dict[str, Any]] = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        user = task if not context else f"{task}\n\nContext:\n{context}"
        messages.append({"role": "user", "content": user})

        res = self._router.complete(
            messages,
            role=self._model_role,
            escalate=self._escalate,
            run_id=run_id,
            task_id=task_id,
            est_usd=est_usd,
            agent=self.role,
        )

        findings = self._parser(res.text)
        # Low confidence → escalate rather than assert. A subagent with no sourceable
        # finding, or only LOW-proof findings, asks for a human/council instead of
        # pretending it succeeded.
        escalated = not findings or all(f.proof_level == ProofLevel.LOW for f in findings)

        return SubagentResult(
            role=self.role,
            findings=findings,
            cost_usd=res.cost_usd or 0.0,
            tokens=res.prompt_tokens + res.completion_tokens,
            escalated=escalated,
        )
