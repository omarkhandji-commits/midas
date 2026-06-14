"""Unified approval-channel base — one security model, many platforms.

Every channel (Telegram, WhatsApp, Discord, Slack, Signal, iMessage, SMS, email…)
does the same job from MIDAS's perspective:

  1. surface pending approvals to the operator;
  2. accept ONE tap that resolves them;
  3. never trust free-form text to approve anything (anti-injection via chat).

Centralizing that logic here means a new adapter just translates platform events into
two calls — `handle_callback(chat_id, data)` and `handle_text(chat_id, text)` — and
gets the security guarantees for free:
- owner-gated (only the configured operator id may resolve);
- callback format strictly parsed (`apv:approve:<id>` / `apv:reject:<id>`);
- idempotency surfaced from the ApprovalQueue;
- text containing "approve #5 please" is REFUSED (matches
  policy.approval.ignore_chat_text_claiming_authority: true).

Renderers are pure functions, fully testable without any network. Platform SDKs are
imported lazily inside each adapter so the dependency set stays optional per channel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from midas.core.approvals import ApprovalError, ApprovalQueue, ApprovalRequest


@dataclass
class ChannelConfig:
    """The two pieces every adapter needs. Add platform-specifics in subclasses."""

    name: str  # e.g. "telegram", "discord"
    owner_id: str  # only this operator id may resolve approvals on this channel


def render_pending(req: ApprovalRequest) -> str:
    payload_preview = ", ".join(f"{k}={v}" for k, v in list(req.payload.items())[:3]) or "(none)"
    return (
        f"#{req.id}  [{req.action}]\n"
        f"agent: {req.agent}   tool: {req.tool}\n"
        f"{req.summary}\n"
        f"payload: {payload_preview}\n"
        f"created: {req.created_ts}"
    )


def render_list(pending: list[ApprovalRequest]) -> str:
    if not pending:
        return "No pending approvals. You're clear."
    blocks = ["Pending approvals (tap to act):"]
    for req in pending:
        blocks.append("─" * 30)
        blocks.append(render_pending(req))
    return "\n".join(blocks)


def parse_callback(data: str) -> tuple[str, int] | None:
    """Decode an inline-button callback. Returns (action, approval_id) or None.

    Format is intentionally strict and identical across platforms: ``apv:approve:42``
    or ``apv:reject:42``. Anything else is ignored — never coerced.
    """
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "apv":
        return None
    if parts[1] not in ("approve", "reject"):
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


def keyboard_buttons(approval_id: int) -> list[dict[str, str]]:
    """Platform-agnostic button data: each adapter maps these to its own widget type."""
    return [
        {"text": "Approve", "callback_data": f"apv:approve:{approval_id}"},
        {"text": "Reject", "callback_data": f"apv:reject:{approval_id}"},
    ]


class ApprovalChannel:
    """Shared owner-gated handler. All channel adapters delegate here.

    Adapters convert platform events to these two calls, never bypass them:
        bot.handle_callback(chat_id, callback_data) -> reply text
        bot.handle_text(chat_id, text)              -> reply text
    """

    def __init__(
        self,
        config: ChannelConfig,
        queue: ApprovalQueue,
        *,
        renderer: Any = None,
    ) -> None:
        self._config = config
        self._queue = queue
        self._render_pending = (renderer or render_pending)

    @property
    def name(self) -> str:
        return self._config.name

    def is_owner(self, chat_id: str) -> bool:
        return str(chat_id) == str(self._config.owner_id)

    def list_pending(self) -> str:
        return render_list(self._queue.pending())

    def handle_callback(self, chat_id: str, data: str) -> str:
        if not self.is_owner(chat_id):
            return "Not authorized."
        parsed = parse_callback(data)
        if parsed is None:
            return "Unrecognized action."
        action, req_id = parsed
        try:
            req = (
                self._queue.approve(req_id, by=str(chat_id))
                if action == "approve"
                else self._queue.reject(req_id, by=str(chat_id))
            )
        except ApprovalError as exc:
            return f"#{req_id}: {exc}"
        return f"#{req.id} {req.status.value} by you (via {self._config.name})."

    def handle_text(self, chat_id: str, text: str) -> str:
        """Text NEVER approves. It can only list. Defense vs prompt-injection in chat."""
        if not self.is_owner(chat_id):
            return "Not authorized."
        if text.strip().lower() in ("list", "/list", "pending", "/pending"):
            return self.list_pending()
        return (
            "Text never approves. Tap the buttons next to a pending item, "
            "or send 'list' to see them."
        )
