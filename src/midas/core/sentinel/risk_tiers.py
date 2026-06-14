"""Classify an action into a risk tier from policy.yml (default-deny on unknown)."""

from __future__ import annotations

from midas.core.config.models import PolicyConfig

from .models import Tier


def classify(action: str, policy: PolicyConfig) -> Tier:
    a = policy.actions
    if action in a.never:
        return Tier.FORBIDDEN
    if action in a.requires_approval:
        return Tier.APPROVE
    if action in a.allowed_without_approval:
        return Tier.AUTO
    # Unknown action → default-deny: route to human approval rather than auto-run.
    return Tier.APPROVE
