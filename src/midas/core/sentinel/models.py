"""Sentinel data models: a tool call to evaluate, and the gate's verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from midas.core.receipts.models import Decision, Taint


class Tier(StrEnum):
    AUTO = "auto"  # reversible reads — run automatically
    NOTIFY = "notify"  # local writes — run, but notify
    APPROVE = "approve"  # irreversible / outbound — require human approval
    FORBIDDEN = "forbidden"  # never allowed


@dataclass
class ToolCall:
    """A request to run a tool, with the trust-relevant facts the Sentinel needs."""

    tool: str
    action: str  # matches the action names in policy.yml (actions.*)
    taints: set[Taint] = field(default_factory=lambda: {Taint.TRUSTED})
    has_private_access: bool = False  # reads secrets / operator data / repo
    has_egress: bool = False  # automatically transmits data outward (not a read-fetch)
    egress_domains: list[str] = field(default_factory=list)
    payload: Any = None


@dataclass
class SentinelDecision:
    decision: Decision
    tier: Tier
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    @property
    def needs_approval(self) -> bool:
        return self.decision == Decision.QUEUE_APPROVAL
