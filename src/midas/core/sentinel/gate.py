"""The Sentinel gate — every tool call passes through `evaluate()`.

Order of checks (fail-closed):
  1. kill switch        → DENY everything
  2. forbidden action   → DENY (policy.actions.never)
  3. lethal trifecta    → DENY unconditionally (even if otherwise approvable)
  4. APPROVE tier       → QUEUE_APPROVAL (human authorizes outbound/irreversible)
  5. AUTO tier + egress → DENY if destination not on the egress allow-list
  6. AUTO tier          → ALLOW
"""

from __future__ import annotations

from typing import Optional

from midas.core.config.models import PolicyConfig
from midas.core.receipts.models import Decision

from .egress import first_blocked_domain
from .killswitch import KillSwitch
from .models import SentinelDecision, Tier, ToolCall
from .risk_tiers import classify
from .trifecta import is_lethal_trifecta


class Sentinel:
    def __init__(self, policy: PolicyConfig, kill_switch: Optional[KillSwitch] = None) -> None:
        self.policy = policy
        self.kill = kill_switch or KillSwitch(policy.kill_switch)

    def evaluate(self, call: ToolCall) -> SentinelDecision:
        if self.kill.engaged:
            return SentinelDecision(Decision.DENY, Tier.FORBIDDEN, "kill switch engaged")

        tier = classify(call.action, self.policy)

        if tier == Tier.FORBIDDEN:
            return SentinelDecision(
                Decision.DENY, Tier.FORBIDDEN, f"action '{call.action}' is forbidden by policy"
            )

        if is_lethal_trifecta(call):
            return SentinelDecision(
                Decision.DENY,
                Tier.FORBIDDEN,
                "lethal trifecta blocked: untrusted content + private access + external egress "
                "in one step (indirect prompt-injection exfiltration risk)",
            )

        if tier == Tier.APPROVE:
            return SentinelDecision(
                Decision.QUEUE_APPROVAL,
                Tier.APPROVE,
                f"action '{call.action}' requires human approval",
            )

        # AUTO tier: no automatic exfiltration to non-allow-listed destinations.
        if call.has_egress:
            blocked = first_blocked_domain(call.egress_domains, self.policy.egress_allowlist)
            if blocked is not None:
                return SentinelDecision(
                    Decision.DENY,
                    Tier.FORBIDDEN,
                    f"automatic egress to non-allow-listed domain blocked: {blocked}",
                )

        return SentinelDecision(Decision.ALLOW, Tier.AUTO, f"action '{call.action}' allowed")
