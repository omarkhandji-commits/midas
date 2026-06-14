"""SMS adapter — Twilio (or any SMS gateway). DSL identical to Signal/iMessage."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, render_list

_CMD = re.compile(r"^(approve|reject)\s+#?(\d+)\s*$", re.IGNORECASE)


@dataclass
class SMSConfig(ChannelConfig):
    account_sid: str = ""  # Twilio
    auth_token: str = ""
    from_number: str = ""  # the Twilio-provisioned number

    @classmethod
    def make(
        cls, *, account_sid: str, auth_token: str, from_number: str, owner_phone: str,
    ) -> SMSConfig:
        return cls(
            name="sms", owner_id=str(owner_phone),
            account_sid=account_sid, auth_token=auth_token, from_number=from_number,
        )


class SMSBot(ApprovalChannel):
    def handle_text(self, chat_id: str, text: str) -> str:
        if not self.is_owner(chat_id):
            return "Not authorized."
        m = _CMD.match(text.strip())
        if m is None:
            if text.strip().lower() in ("list", "pending"):
                return render_list(self._queue.pending())
            return "SMS: send 'approve 42' or 'reject 42'."
        action, req_id = m.group(1).lower(), int(m.group(2))
        return self.handle_callback(chat_id, f"apv:{action}:{req_id}")


__all__ = ["SMSBot", "SMSConfig"]
