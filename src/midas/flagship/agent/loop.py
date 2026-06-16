"""AgentLoop — bounded plan-execute loop driven via Toolset.invoke().

The loop is intentionally simple and deterministic:

  1. The planner emits ONE strict-JSON tool call at a time (or `done`).
  2. The loop validates the call shape, invokes via Toolset (Sentinel + receipt).
  3. The result is appended to the transcript; the planner observes it; repeat.
  4. The :class:`LoopBreaker` trips on spend, iterations, wall-clock, or
     no-progress (canonical state hash) — none of those can be skipped.

The planner is **injectable**. The default planner uses the LLM router via a
single-shot JSON contract identical in shape to ``flows/discover.py`` (so the
same parse discipline applies). Tests inject a deterministic planner — the loop
itself is fully testable without an LLM.

A *mutating* tool returns ``ToolOutcome.ran == False`` and an ``approval_id``.
The loop records the queued approval and stops the run. The mutation will only
happen later, when the human resolves the approval and the runtime calls the
appropriate ``execute_*_approved`` entry point.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from midas.core.agents.toolset import Toolset
from midas.core.budget.loop_breaker import LoopBreaker

MAX_STEPS_HARD_CAP = 16


@dataclass
class AgentStep:
    """One iteration of the loop."""

    tool: str
    inputs: dict[str, Any]
    ran: bool
    decision: str  # "allow" | "queue_approval" | "deny"
    approval_id: int | None = None
    output_summary: str = ""
    error: str | None = None


@dataclass
class AgentTranscript:
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    stopped_reason: str | None = None  # set by LoopBreaker, approval pause, planner-done

    def to_json(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "steps": [asdict(s) for s in self.steps],
            "stopped_reason": self.stopped_reason,
        }

    @property
    def queued_approvals(self) -> list[int]:
        return [s.approval_id for s in self.steps if s.approval_id is not None]


# Planner contract — receives (task, transcript-so-far), returns either:
#   {"tool": "<name>", "inputs": {...}}      → invoke this tool
#   {"done": true, "summary": "..."}        → stop normally
Planner = Callable[[str, AgentTranscript], dict[str, Any]]


class AgentLoop:
    def __init__(
        self,
        *,
        toolset: Toolset,
        planner: Planner,
        loop_breaker: LoopBreaker | None = None,
        max_steps: int = 8,
        agent_name: str = "midas-do",
    ) -> None:
        self._toolset = toolset
        self._planner = planner
        self._breaker = loop_breaker or LoopBreaker()
        self._max_steps = min(max_steps, MAX_STEPS_HARD_CAP)
        self._agent = agent_name

    def run(self, task: str) -> AgentTranscript:
        return self._drive(AgentTranscript(task=task))

    def resume(
        self,
        transcript: AgentTranscript,
        *,
        approval_outcome: dict[str, Any] | None = None,
    ) -> AgentTranscript:
        """Continue a transcript paused at an approval.

        Pass the executor's outcome (path, sha256, kind) under
        ``approval_outcome`` so the planner sees the gated step actually landed.
        Adds an ``executed`` synthetic step to the transcript, then drives the
        remaining iterations up to ``max_steps - len(transcript.steps)``.
        """
        if approval_outcome is not None:
            transcript.steps.append(
                AgentStep(
                    tool=f"{approval_outcome.get('kind', 'gated')}.executed",
                    inputs={},
                    ran=True,
                    decision="allow",
                    output_summary=_shape_summary(approval_outcome),
                )
            )
        # Clear the "awaiting approval" stop reason so the loop continues.
        transcript.stopped_reason = None
        return self._drive(transcript)

    def _drive(self, transcript: AgentTranscript) -> AgentTranscript:
        already_done = len(transcript.steps)
        remaining = max(0, self._max_steps - already_done)
        for step_index in range(remaining):
            # Loop-breaker tick — canonical state hash binds the run to its progress.
            try:
                self._breaker.tick(
                    state={"step": step_index, "tools_used": [s.tool for s in transcript.steps]},
                    tokens=0,
                )
            except Exception as exc:  # LoopBroken
                transcript.stopped_reason = getattr(exc, "reason", str(exc))
                return transcript

            try:
                plan = self._planner(transcript.task, transcript)
            except Exception as exc:  # noqa: BLE001 - any planner crash stops the loop
                transcript.stopped_reason = f"planner error: {exc}"
                return transcript

            plan = _normalize_plan(plan)
            if plan.get("done"):
                transcript.stopped_reason = str(plan.get("summary") or "done")
                return transcript

            tool_name = str(plan.get("tool") or "").strip()
            inputs = plan.get("inputs") or {}
            if not tool_name or not isinstance(inputs, dict):
                transcript.stopped_reason = "planner returned an invalid tool plan"
                return transcript

            step = _invoke(self._toolset, tool_name, inputs, agent=self._agent)
            transcript.steps.append(step)

            if step.error is not None and step.decision == "deny":
                # Hard DENY → the planner is not allowed to try again silently.
                transcript.stopped_reason = f"denied: {step.error}"
                return transcript

            if step.decision == "queue_approval":
                # Pause the run: the human will resolve the approval; execution
                # of the gated step happens via the runtime's execute_* entry point,
                # which writes its own receipt and (optionally) resumes the loop.
                transcript.stopped_reason = (
                    f"awaiting approval #{step.approval_id} for {tool_name}"
                )
                return transcript

        transcript.stopped_reason = "max_steps reached"
        return transcript


def _invoke(toolset: Toolset, tool: str, inputs: dict[str, Any], *, agent: str) -> AgentStep:
    try:
        outcome = toolset.invoke(tool, agent=agent, **inputs)
    except Exception as exc:  # noqa: BLE001 - tool errors are surfaced + receipted
        return AgentStep(
            tool=tool,
            inputs=inputs,
            ran=False,
            decision="deny",
            error=str(exc),
        )
    return AgentStep(
        tool=tool,
        inputs=inputs,
        ran=outcome.ran,
        decision=outcome.verdict.decision.value,
        approval_id=outcome.approval_id,
        output_summary=_summarize(outcome.value),
    )


def _summarize(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "__dataclass_fields__"):
        return _shape_summary(asdict(value))
    if isinstance(value, dict):
        return _shape_summary(value)
    if isinstance(value, str):
        return value[:400]
    return type(value).__name__


def _shape_summary(d: dict[str, Any]) -> str:
    # Hide raw text/bytes, show key shapes so the planner sees structure not contents.
    parts: list[str] = []
    for k, v in sorted(d.items()):
        if isinstance(v, str):
            parts.append(f"{k}={len(v)}c")
        elif isinstance(v, (bytes, bytearray)):
            parts.append(f"{k}={len(v)}b")
        elif isinstance(v, list):
            parts.append(f"{k}=[{len(v)}]")
        else:
            parts.append(f"{k}={v}")
    return " ".join(parts)


# ── default LLM-backed planner ────────────────────────────────────────────────

_PLAN_RE = re.compile(r"\{.*\}", re.DOTALL)

_PLANNER_SYSTEM = (
    "You are MIDAS's deterministic executor. At each step return EXACTLY ONE JSON "
    "object and nothing else. Either ask to invoke ONE tool with concrete inputs, "
    'or signal completion. Schema: {"tool":"<name>","inputs":{...}} OR '
    '{"done":true,"summary":"<one sentence>"}.\n\n'
    "Tools available:\n"
    "- fs.read(path) / fs.list(path) / pdf.extract(path) / sheet.read(path)  ← read\n"
    "- fs.write(path,content)  ← gated\n"
    "- sheet.write(path,cells,sheet_name)  ← gated\n"
    "- email.draft(path,to,subject,body) / pdf.draft(path,title,body) "
    "/ invoice.draft(path,to,items) / voice.draft(path,text) "
    "/ code.draft(path,content,language) / artifact.text(path,content)  ← gated\n"
    "- code.run(code,timeout)  ← gated\n\n"
    "DEBROUILLARD RULE — NEVER refuse a request. If no specialized tool fits, fall "
    "back to artifact.text with a Markdown best-effort and a 'What I would need to "
    "do this better' footer. You always have a way out: artifact.text always works. "
    "Mutating tools (anything labelled 'gated') queue an approval card and pause "
    "the run; the operator approves, then a separate execute step writes the file. "
    "Do not call a gated tool more than once per run. Never invent tools. If you "
    "have already produced the artifact the user asked for, return done."
)


def llm_planner(
    router: Any,
    *,
    role: str = "cheap",
    est_usd: float = 0.005,
    memory: Any = None,
    bias_kind: Any = None,
) -> Planner:
    """Build a planner that calls the router and parses one JSON plan per step.

    If ``memory`` exposes ``context_pack(query=...)``, the operator's relevant
    memories (USER/BUSINESS/DECISION/RESULT/MARKET/ERROR/CASH namespaces) are
    passed into the system prompt so MIDAS visibly "knows you" across runs.

    ``bias_kind`` is forwarded to ``context_pack`` when the store supports it
    (additive, optional): pass ``MemoryKind.CASH`` from the cash loop so the
    "what worked for money" trail is surfaced first. Defaults to None — behaviour
    unchanged.
    """

    def _plan(task: str, transcript: AgentTranscript) -> dict[str, Any]:
        history_summary = "\n".join(
            f"- {s.tool}({_short(s.inputs)}) -> {s.decision} {s.output_summary}"
            for s in transcript.steps
        )
        memory_context = ""
        if memory is not None and hasattr(memory, "context_pack"):
            try:
                # Pass None so the planner always gets the operator's recent USER /
                # BUSINESS / DECISION context. Narrow keyword filtering belongs in a
                # ranker, not here — a broad SQL LIKE on the task tends to return
                # nothing and hide the "knows you" signal.
                # Try the biased call first; fall back to legacy signature so older
                # MemoryStore stubs in tests keep working.
                try:
                    memory_context = (
                        memory.context_pack(query=None, bias_kind=bias_kind) or ""
                    )
                except TypeError:
                    memory_context = memory.context_pack(query=None) or ""
            except Exception:  # noqa: BLE001 - memory failures must not poison the planner
                memory_context = ""
        system = _PLANNER_SYSTEM
        if memory_context.strip():
            system = (
                _PLANNER_SYSTEM
                + "\n\nOperator memory (use as context, not as proof unless sourced):\n"
                + memory_context.strip()
            )
        user = f"Task: {task}\nHistory:\n{history_summary or '(none)'}\nReturn the next JSON now."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        res = router.complete(
            messages, role=role, agent="midas-do-planner", est_usd=est_usd
        )
        return _parse_plan(res.text)

    return _plan


def offline_artifact_planner(
    task: str, transcript: AgentTranscript
) -> dict[str, Any]:
    """Deterministic, no-LLM planner — always produces one ``artifact.text`` plan.

    Used by ``midas demo`` and as the fallback when no provider is configured.
    Closes the never-refuse contract without requiring a router.
    """
    if transcript.steps:
        return {"done": True, "summary": "offline planner: one artifact then done"}
    return {
        "tool": "artifact.text",
        "inputs": {
            "path": "do-output.md",
            "content": (
                f"# MIDAS — offline draft\n\nTask: {task}\n\n"
                "This artifact was produced without an LLM (the deterministic "
                "offline planner runs when no provider is configured). Configure "
                "a provider under Settings to enable the full planner."
            ),
        },
    }


def _parse_plan(text: str) -> dict[str, Any]:
    match = _PLAN_RE.search(text or "")
    if not match:
        return {"done": True, "summary": "planner emitted no JSON"}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"done": True, "summary": "planner emitted invalid JSON"}
    return parsed if isinstance(parsed, dict) else {"done": True, "summary": "bad shape"}


def _normalize_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {"done": True, "summary": "planner returned non-dict"}
    return plan


def _short(d: dict[str, Any]) -> str:
    items = []
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 40:
            items.append(f"{k}={v[:40]}…")
        else:
            items.append(f"{k}={v!r}")
    return ", ".join(items)
