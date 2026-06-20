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
# New shape: ```action\n{...}\n```. Easier on the LLM (it's already producing
# markdown) and cleaner to extract — see _extract_action_block.
_ACTION_BLOCK_RE = re.compile(r"```action\s*\n(.*?)\n```", re.DOTALL)


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
    # New markdown-friendly extraction first, then the legacy APPROVAL_REQUIRED
    # marker, then a heuristic fallback. Order matters: the new shape is what we
    # tell the model to emit in the rewritten system prompt below.
    text, requested = _extract_action_block(result.text)
    if requested is None:
        text, requested = _extract_approval(text)
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
            "content": _SYSTEM_PROMPT,
        },
        *clean_history,
        {"role": "user", "content": message},
    ]


_SYSTEM_PROMPT = (
    "You are MIDAS, a proof-first business operator running locally on the user's "
    "machine. You talk like a normal helpful assistant — clear, friendly, brief. "
    "Format your replies as Markdown: headings, bullet lists, fenced code blocks, "
    "and GitHub-flavored tables when they help. Be honest about uncertainty, never "
    "guarantee revenue, never claim an external action has been executed.\n\n"
    "When you want to PROPOSE a risky or outbound action (sending email, posting "
    "publicly, calling someone, writing files, spending money), do NOT execute it. "
    "Append ONE fenced block at the end of your reply:\n\n"
    "```action\n"
    "{\n"
    '  "tool": "email",\n'
    '  "action": "send_email",\n'
    '  "summary": "Short one-line description",\n'
    '  "payload": {"draft": "<the actual draft>"}\n'
    "}\n"
    "```\n\n"
    "MIDAS will surface that block as an approval card. The user reviews and "
    "decides — only then does the action run. If no risky action is needed, "
    "do not emit any action block."
)


def _extract_action_block(text: str) -> tuple[str, dict[str, Any] | None]:
    """Parse the new ```action {...} ``` fenced block format.

    The block is stripped from the visible text so the operator sees clean
    markdown without the JSON. Returns ``(visible_text, action_dict_or_None)``.
    Falls back gracefully on malformed JSON inside the fence.
    """
    match = _ACTION_BLOCK_RE.search(text)
    if match is None:
        return text, None
    visible = (text[: match.start()] + text[match.end():]).strip()
    try:
        payload = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return visible, None
    if not isinstance(payload, dict):
        return visible, None
    return visible, _normalise_requested_action(payload)


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
