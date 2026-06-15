"""Sprint F3 — AgentLoop planner is grounded in operator memory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from midas.core.memory import MemoryKind, MemoryStore
from midas.core.router.models import ChatResult
from midas.flagship.agent.loop import llm_planner


class _SpyRouter:
    """Captures the messages sent to the LLM so we can assert the prompt shape."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], **_kwargs: Any) -> ChatResult:
        self.calls.append(messages)
        return ChatResult(
            text='{"done": true, "summary": "noop"}',
            model="stub",
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
        )


def test_planner_injects_memory_context(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "memory.db")
    # context_pack(query=...) filters by LIKE — seed memory that overlaps the task.
    memory.remember(
        MemoryKind.USER,
        "outreach-voice",
        "Operator prefers sober outreach copy, no emojis.",
    )
    memory.remember(
        MemoryKind.BUSINESS,
        "outreach-icp",
        "Outreach targets boutique law firms in Montreal.",
    )
    router = _SpyRouter()
    planner = llm_planner(router, memory=memory)

    from midas.flagship.agent.loop import AgentTranscript

    planner("Draft a cold outreach", AgentTranscript(task="Draft a cold outreach"))

    assert router.calls, "planner must have called the router"
    system_msg = router.calls[0][0]["content"]
    assert "Operator memory" in system_msg
    assert "sober outreach" in system_msg
    assert "boutique law firms" in system_msg


def test_planner_works_without_memory() -> None:
    router = _SpyRouter()
    planner = llm_planner(router, memory=None)
    from midas.flagship.agent.loop import AgentTranscript

    plan = planner("anything", AgentTranscript(task="anything"))
    assert plan == {"done": True, "summary": "noop"}
    # No memory context appended.
    system_msg = router.calls[0][0]["content"]
    assert "Operator memory" not in system_msg


def test_planner_tolerates_failing_memory() -> None:
    """A broken memory must never poison the planner — silently fall back."""

    class _BrokenMemory:
        def context_pack(self, *_a: Any, **_k: Any) -> str:
            raise RuntimeError("memory backend down")

    router = _SpyRouter()
    planner = llm_planner(router, memory=_BrokenMemory())
    from midas.flagship.agent.loop import AgentTranscript

    plan = planner("anything", AgentTranscript(task="anything"))
    assert plan == {"done": True, "summary": "noop"}
    # Planner still ran; no memory section appended.
    assert "Operator memory" not in router.calls[0][0]["content"]
