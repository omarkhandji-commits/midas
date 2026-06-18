"""Toolset — the ONLY way an agent can run a tool.

Security invariant (release gate): no tool is callable except through
`Toolset.invoke()`, which always passes the call through the Sentinel first and
writes a receipt for the verdict. A tool whose Sentinel verdict is DENY never runs;
a tool whose verdict is QUEUE_APPROVAL never runs automatically (it is parked for a
human). Only ALLOW actually invokes the underlying callable.

This is what makes indirect prompt-injection exfiltration structurally hard: even a
fully hijacked agent can only *ask* the toolset to run something, and the Sentinel —
not the model — decides.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from midas.core.receipts.models import Decision, Taint
from midas.core.sentinel.gate import Sentinel
from midas.core.sentinel.models import SentinelDecision, ToolCall


class ToolDenied(Exception):
    """Raised when the Sentinel denies a tool call (the tool never ran)."""

    def __init__(self, tool: str, verdict: SentinelDecision) -> None:
        super().__init__(f"tool '{tool}' denied by sentinel: {verdict.reason}")
        self.tool = tool
        self.verdict = verdict


@dataclass
class Tool:
    """A callable plus the trust facts the Sentinel needs to judge it."""

    name: str
    action: str  # must match an action name in policy.yml (actions.*)
    fn: Callable[..., Any]
    has_private_access: bool = False
    has_egress: bool = False
    egress_domains: list[str] = field(default_factory=list)
    # The trust label of THIS tool's output (e.g. web_fetch → UNTRUSTED).
    output_taint: Taint = Taint.TRUSTED
    prepares_approval_payload: bool = False


@dataclass
class ToolOutcome:
    """The result of an `invoke()`. `ran` is False for DENY / QUEUE_APPROVAL."""

    tool: str
    verdict: SentinelDecision
    ran: bool
    value: Any = None
    output_taint: Taint = Taint.TRUSTED
    approval_id: int | None = None  # set when the call was parked in the approval queue


class Toolset:
    def __init__(
        self,
        sentinel: Sentinel,
        *,
        ledger: Any = None,  # core.receipts.ReceiptLedger (optional)
        approvals: Any = None,  # core.approvals.ApprovalQueue (optional)
        run_id: str = "",
    ) -> None:
        self._sentinel = sentinel
        self._ledger = ledger
        self._approvals = approvals
        self._run_id = run_id
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def invoke(
        self,
        name: str,
        *,
        agent: str = "agent",
        input_taints: set[Taint] | None = None,
        **kwargs: Any,
    ) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            # Default-deny on an unknown tool — never fall through to calling it.
            raise ToolDenied(name, _unknown_verdict(name))

        taints = set(input_taints or {Taint.TRUSTED})
        call = ToolCall(
            tool=tool.name,
            action=tool.action,
            taints=taints,
            has_private_access=tool.has_private_access,
            has_egress=tool.has_egress,
            egress_domains=list(tool.egress_domains),
            payload=kwargs,
        )
        verdict = self._sentinel.evaluate(call)

        if not verdict.allowed:
            self._receipt(agent, tool, verdict, ran=False, taint_in=_max_taint(taints))
            if verdict.needs_approval:
                # Park the call in the persistent queue (single source of truth across
                # CLI, Telegram, dashboard). The underlying callable never runs here —
                # a human resolves the queue, then a separate execute step fires.
                approval_id: int | None = None
                if self._approvals is not None:
                    payload = dict(kwargs)
                    if tool.prepares_approval_payload:
                        payload.update(_payload_dict(tool.fn(**kwargs)))
                    req = self._approvals.enqueue(
                        run_id=self._run_id, agent=agent, tool=tool.name, action=tool.action,
                        summary=_approval_summary(agent, tool, payload), payload=payload,
                    )
                    approval_id = req.id
                return ToolOutcome(tool.name, verdict, ran=False, approval_id=approval_id)
            raise ToolDenied(tool.name, verdict)

        value = tool.fn(**kwargs)
        self._receipt(
            agent, tool, verdict, ran=True, taint_in=_max_taint(taints), taint_out=tool.output_taint
        )
        return ToolOutcome(
            tool.name, verdict, ran=True, value=value, output_taint=tool.output_taint
        )

    def _receipt(
        self,
        agent: str,
        tool: Tool,
        verdict: SentinelDecision,
        *,
        ran: bool,
        taint_in: Taint,
        taint_out: Taint = Taint.TRUSTED,
    ) -> None:
        if self._ledger is None:
            return
        self._ledger.append(
            run_id=self._run_id,
            agent=agent,
            tool=tool.name,
            decision=verdict.decision,
            inputs={"action": tool.action, "ran": ran},
            outputs={"reason": verdict.reason},
            taint_in=taint_in,
            taint_out=taint_out,
        )


def _max_taint(taints: set[Taint]) -> Taint:
    if Taint.UNTRUSTED in taints:
        return Taint.UNTRUSTED
    if Taint.PRIVATE in taints:
        return Taint.PRIVATE
    return Taint.TRUSTED


def _unknown_verdict(name: str) -> SentinelDecision:
    from midas.core.sentinel.models import Tier

    return SentinelDecision(
        Decision.DENY, Tier.FORBIDDEN, f"unknown tool '{name}' (not registered in toolset)"
    )


def _payload_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"approval planner returned unsupported payload: {type(value).__name__}")


def _approval_summary(agent: str, tool: Tool, payload: dict[str, Any]) -> str:
    preview = str(payload.get("preview") or "").strip()
    if preview:
        return f"{agent}: {tool.name} approval - {preview[:120]}"
    return f"{agent}: {tool.action} on {tool.name}"
