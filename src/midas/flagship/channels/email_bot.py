"""Email adapter — owner-only approve/reject via signed-link or reply DSL.

Email has zero interactive widgets that work across all clients; we use the same
constrained-text DSL (`approve 42` / `reject 42`) on the inbound side, parsed when the
production runtime feeds us replies. Outbound notification messages include both DSL
hints and an HTTPS link the dashboard can serve as a one-click approve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, render_list

_CMD = re.compile(r"^(approve|reject)\s+#?(\d+)\s*$", re.IGNORECASE)


@dataclass
class EmailConfig(ChannelConfig):
    smtp_host: str = ""
    smtp_user: str = ""
    smtp_pass: str = ""

    @classmethod
    def make(cls, *, owner_email: str, smtp_host: str = "",
             smtp_user: str = "", smtp_pass: str = "") -> EmailConfig:
        return cls(
            name="email", owner_id=str(owner_email),
            smtp_host=smtp_host, smtp_user=smtp_user, smtp_pass=smtp_pass,
        )


class EmailBot(ApprovalChannel):
    def handle_text(self, chat_id: str, text: str) -> str:
        if not self.is_owner(chat_id):
            return "Not authorized."
        # Email replies often contain quoted history — scan only the first non-quote line.
        first_line = next(
            (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith(">")),
            "",
        )
        m = _CMD.match(first_line)
        if m is None:
            if first_line.lower() in ("list", "pending"):
                return render_list(self._queue.pending())
            return "Email: reply with 'approve 42' or 'reject 42' on the FIRST line."
        action, req_id = m.group(1).lower(), int(m.group(2))
        return self.handle_callback(chat_id, f"apv:{action}:{req_id}")


__all__ = ["EmailBot", "EmailConfig"]
