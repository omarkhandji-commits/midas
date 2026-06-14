"""Adaptive council — wraps the multi-LLM deliberation pattern (à la karpathy/llm-council
and togethercomputer/MoA), but convened only when stakes justify it, budgeted, and with
*disagreement as a signal to escalate to a human* rather than guess.

The council is NOT run on every token (that's the expensive MoA mistake). The supervisor
calls `deliberate()` only for high-stakes/low-confidence decisions, within the budget fuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .models import ChatResult
from .router import LLMRouter, Messages

SimilarityFn = Callable[[str, str], float]


@dataclass
class CouncilResult:
    answers: list[ChatResult]
    final: ChatResult
    agreement: float  # 0..1 — mean pairwise similarity of member answers
    escalate_to_human: bool


def _exact_similarity(a: str, b: str) -> float:
    return 1.0 if a == b else 0.0


class Council:
    def __init__(
        self,
        router: LLMRouter,
        members: list[str],
        chairman: str,
        *,
        agreement_threshold: float = 0.5,
    ) -> None:
        self.router = router
        self.members = members
        self.chairman = chairman
        self.agreement_threshold = agreement_threshold

    def deliberate(
        self,
        messages: Messages,
        *,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        est_usd_each: float = 0.0,
        similarity_fn: Optional[SimilarityFn] = None,
    ) -> CouncilResult:
        answers = [
            self.router.complete_model(
                m, messages, task_id=task_id, run_id=run_id, est_usd=est_usd_each, agent="council"
            )
            for m in self.members
        ]
        agreement = self._agreement(answers, similarity_fn or _exact_similarity)

        synthesis_messages: Messages = [*messages, {"role": "user", "content": self._prompt(answers)}]
        final = self.router.complete_model(
            self.chairman,
            synthesis_messages,
            task_id=task_id,
            run_id=run_id,
            est_usd=est_usd_each,
            agent="council-chairman",
        )
        return CouncilResult(
            answers=answers,
            final=final,
            agreement=agreement,
            escalate_to_human=agreement < self.agreement_threshold,
        )

    @staticmethod
    def _agreement(answers: list[ChatResult], sim: SimilarityFn) -> float:
        texts = [a.text.strip().lower() for a in answers]
        if len(texts) < 2:
            return 1.0
        pairs = [(i, j) for i in range(len(texts)) for j in range(i + 1, len(texts))]
        return sum(sim(texts[i], texts[j]) for i, j in pairs) / len(pairs)

    @staticmethod
    def _prompt(answers: list[ChatResult]) -> str:
        blob = "\n\n".join(f"[Member {i + 1}]\n{a.text}" for i, a in enumerate(answers))
        return (
            "You are the Chairman of an LLM council. Synthesize the single best, correct answer "
            "from the anonymized member responses below. Resolve disagreements on the merits; do "
            "not invent facts.\n\n" + blob
        )
