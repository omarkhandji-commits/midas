"""Sentinel — the security gate every tool call passes through."""

from midas.core.receipts.models import Taint

from .egress import domain_allowed, first_blocked_domain
from .gate import Sentinel
from .killswitch import KillSwitch
from .models import SentinelDecision, Tier, ToolCall
from .secrets_broker import SecretsBroker
from .trifecta import is_lethal_trifecta

__all__ = [
    "Sentinel",
    "SentinelDecision",
    "Tier",
    "ToolCall",
    "Taint",
    "KillSwitch",
    "SecretsBroker",
    "is_lethal_trifecta",
    "domain_allowed",
    "first_blocked_domain",
]
