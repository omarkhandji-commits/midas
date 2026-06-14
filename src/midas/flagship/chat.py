"""Proof-first dashboard chat service.

The chat endpoint is not a tool-execution loophole. It can call the LLM router and
draft text, but risky actions are turned into ApprovalQueue cards after Sentinel
evaluation. Nothing outbound runs from chat.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from midas.core.approvals import ApprovalRequest
from midas.core.receipts.models import Decision
from midas.core.router import LLMRouter
from midas.core.sentinel import Sentinel, ToolCall

_APPROVAL_PREFIX = "APPROVAL_REQUIRED:"
_APPROVAL_RE = re.compile(r"APPROVAL_REQUIRED:\s*(\{.*\})", re.DOTALL)


@dataclass(frozen=True)
class ChatApproval:
    id: int
    run_id: str
    agent: str
    tool: str
    action: str
    summary: str
    payload: dict[str, Any]
    status: str
    created_ts: str

    @classmethod
    def from_request(cls, request: ApprovalRequest) -> ChatApproval:
        return cls(
            id=request.id,
            run_id=request.run_id,
            agent=request.agent,
            tool=request.tool,
            action=request.action,
            summary=request.summary,
            payload=request.payload,
            status=request.status.value,
            created_ts=request.created_ts,
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatBundle:
    run_id: str
    text: str
    approval: ChatApproval | None
    proof_level: str
    sources: list[str]
    cost_usd: float


def run_chat(
    *,
    message: str,
    history: list[dict[str, str]],
    router: LLMRouter,
    sentinel: Sentinel,
    approvals: Any,
    ledger: Any,
    run_id: str,
    est_usd: float,
) -> ChatBundle:
    messages = _messages(message, history)
    result = router.complete(
        messages,
        role="cheap",
        task_id=run_id,
        run_id=run_id,
        est_usd=est_usd,
        agent="dashboard-chat",
    )
    text, requested = _extract_approval(result.text)
    requested = requested or _infer_risky_action(message, text)
    approval = _queue_approval(
        requested,
        run_id=run_id,
        sentinel=sentinel,
        approvals=approvals,
        ledger=ledger,
    )
    return ChatBundle(
        run_id=run_id,
        text=text.strip() or "I drafted the response and kept risky actions gated.",
        approval=approval,
        proof_level="LOW",
        sources=[],
        cost_usd=float(result.cost_usd or 0.0),
    )


def _messages(message: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    clean_history = [
        {"role": item.get("role", "user"), "content": str(item.get("content", ""))[:4000]}
        for item in history[-8:]
        if item.get("role") in {"user", "assistant"}
    ]
    return [
        {
            "role": "system",
            "content": (
                "You are MIDAS, a proof-first business operator. Draft useful work, "
                "state uncertainty, do not guarantee revenue, and never claim an "
                "external action has been executed. If you propose a risky or outbound "
                "action, add one final line exactly like: "
                f"{_APPROVAL_PREFIX} "
                '{"tool":"email","action":"send_email","summary":"Send prepared email",'
                '"payload":{"draft":"..."}}'
            ),
        },
        *clean_history,
        {"role": "user", "content": message},
    ]


def _extract_approval(text: str) -> tuple[str, dict[str, Any] | None]:
    match = _APPROVAL_RE.search(text)
    if match is None:
        return text, None
    visible = text[: match.start()].rstrip()
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return visible, None
    return visible, _normalise_requested_action(payload)


def _infer_risky_action(message: str, text: str) -> dict[str, Any] | None:
    lower = message.lower()
    if any(needle in lower for needle in ("send email", "send an email", "envoie un email")):
        return {
            "tool": "email",
            "action": "send_email",
            "summary": "Send the prepared email draft.",
            "payload": {"draft": text[:4000]},
        }
    if any(needle in lower for needle in ("publish", "post publicly", "publie")):
        return {
            "tool": "publishing",
            "action": "publish_public",
            "summary": "Publish the prepared public content.",
            "payload": {"draft": text[:4000]},
        }
    if any(needle in lower for needle in ("call this", "phone call", "appel")):
        return {
            "tool": "phone",
            "action": "contact_prospect",
            "summary": "Contact a prospect by phone.",
            "payload": {"script": text[:4000]},
        }
    return None


def _queue_approval(
    requested: dict[str, Any] | None,
    *,
    run_id: str,
    sentinel: Sentinel,
    approvals: Any,
    ledger: Any,
) -> ChatApproval | None:
    if requested is None:
        return None
    tool = str(requested["tool"])
    action = str(requested["action"])
    payload = requested.get("payload") if isinstance(requested.get("payload"), dict) else {}
    summary = str(requested.get("summary") or f"{action} via {tool}")[:500]
    decision = sentinel.evaluate(
        ToolCall(
            tool=tool,
            action=action,
            has_egress=action
            in {"send_email", "send_message", "contact_prospect", "publish_public"},
            payload=payload,
        )
    )
    if ledger is not None:
        ledger.append(
            run_id=run_id,
            agent="dashboard-chat",
            tool=tool,
            decision=decision.decision,
            inputs={"action": action},
            outputs={"sentinel": decision.reason},
        )
    if decision.decision != Decision.QUEUE_APPROVAL:
        return None
    req = approvals.enqueue(
        run_id=run_id,
        agent="dashboard-chat",
        tool=tool,
        action=action,
        summary=summary,
        payload=payload,
    )
    return ChatApproval.from_request(req)


def _normalise_requested_action(payload: dict[str, Any]) -> dict[str, Any] | None:
    tool = str(payload.get("tool") or "").strip()
    action = str(payload.get("action") or "").strip()
    if not tool or not action:
        return None
    raw_payload = payload.get("payload")
    return {
        "tool": tool,
        "action": action,
        "summary": str(payload.get("summary") or f"{action} via {tool}"),
        "payload": raw_payload if isinstance(raw_payload, dict) else {},
    }
