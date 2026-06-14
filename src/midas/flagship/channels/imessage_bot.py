"""iMessage adapter — macOS-only. Same DSL as Signal (no native buttons).

iMessage has no API; this adapter is meant to be driven by an AppleScript / osascript
shim on macOS that delivers incoming messages to `handle_text`. The DSL is identical
to Signal so the operator's mental model stays consistent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, render_list

_CMD = re.compile(r"^(approve|reject)\s+#?(\d+)\s*$", re.IGNORECASE)


@dataclass
class IMessageConfig(ChannelConfig):
    @classmethod
    def make(cls, *, owner_phone_or_email: str) -> IMessageConfig:
        return cls(name="imessage", owner_id=str(owner_phone_or_email))


class IMessageBot(ApprovalChannel):
    def handle_text(self, chat_id: str, text: str) -> str:
        if not self.is_owner(chat_id):
            return "Not authorized."
        m = _CMD.match(text.strip())
        if m is None:
            if text.strip().lower() in ("list", "pending"):
                return render_list(self._queue.pending())
            return (
                "iMessage channel: send 'approve 42' or 'reject 42' (exact format). "
                "Free chat never approves anything."
            )
        action, req_id = m.group(1).lower(), int(m.group(2))
        return self.handle_callback(chat_id, f"apv:{action}:{req_id}")


__all__ = ["IMessageBot", "IMessageConfig"]
