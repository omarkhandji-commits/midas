"""Signal adapter — talks to a local `signal-cli` daemon (HTTP REST mode).

Signal has no native button widgets. We use text + a small DSL that the operator types
back: `approve 42` or `reject 42`. The adapter converts those texts into the SAME
generic callback used by the rest of the channels, so the SECURITY model is identical:
- owner-gated;
- text DSL is parsed strictly here (no fuzzy matching, no "approve please");
- anything else falls through to the base-class "Text never approves" guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, render_list

_CMD = re.compile(r"^(approve|reject)\s+#?(\d+)\s*$", re.IGNORECASE)


@dataclass
class SignalConfig(ChannelConfig):
    daemon_url: str = "http://localhost:8080"

    @classmethod
    def make(cls, *, daemon_url: str, owner_phone: str) -> SignalConfig:
        return cls(name="signal", owner_id=str(owner_phone), daemon_url=daemon_url)


class SignalBot(ApprovalChannel):
    """Same security model as Telegram. The DSL is a CONSTRAINED command, not free chat."""

    def __init__(self, config: SignalConfig, queue, **kw) -> None:
        super().__init__(config, queue, **kw)
        self._config: SignalConfig = config

    def handle_text(self, chat_id: str, text: str) -> str:
        if not self.is_owner(chat_id):
            return "Not authorized."
        m = _CMD.match(text.strip())
        if m is None:
            # Fall back to the normal "text-never-approves" guard (lists or refusal).
            if text.strip().lower() in ("list", "pending"):
                return render_list(self._queue.pending())
            return (
                "Signal channel: send 'approve 42' or 'reject 42' (exact format). "
                "Free chat never approves anything. Send 'list' to see pending."
            )
        action, req_id = m.group(1).lower(), int(m.group(2))
        return self.handle_callback(chat_id, f"apv:{action}:{req_id}")


__all__ = ["SignalBot", "SignalConfig"]
