"""The lethal trifecta rule (Willison): the single most important safety check.

If one step combines (1) access to private data, (2) the ability to send data out, and
(3) untrusted content in scope, an indirect prompt injection can exfiltrate secrets.
Such a step is denied unconditionally — even if it would otherwise be approved.
"""

from __future__ import annotations

from midas.core.receipts.models import Taint

from .models import ToolCall


def is_lethal_trifecta(call: ToolCall) -> bool:
    return call.has_private_access and call.has_egress and (Taint.UNTRUSTED in call.taints)
