"""Sentinel gate: trifecta, egress deny-by-default, risk tiers, kill switch."""

from __future__ import annotations

from pathlib import Path

from midas.core.config import load_policy
from midas.core.receipts.models import Decision
from midas.core.sentinel import KillSwitch, Sentinel, Taint, ToolCall, domain_allowed
from midas.core.sentinel.models import Tier

BASE = Path(__file__).resolve().parents[2]


def _policy(**overrides):
    p = load_policy(BASE / "config" / "policy.yml")
    return p.model_copy(update=overrides) if overrides else p


def _sentinel(**overrides) -> Sentinel:
    return Sentinel(_policy(**overrides))


def test_forbidden_action_denied() -> None:
    d = _sentinel().evaluate(ToolCall(tool="x", action="spam"))
    assert d.decision == Decision.DENY and d.tier == Tier.FORBIDDEN


def test_auto_read_allowed() -> None:
    d = _sentinel().evaluate(ToolCall(tool="search", action="web_search"))
    assert d.decision == Decision.ALLOW and d.tier == Tier.AUTO


def test_outbound_action_requires_approval() -> None:
    d = _sentinel().evaluate(ToolCall(tool="email", action="send_email"))
    assert d.decision == Decision.QUEUE_APPROVAL and d.tier == Tier.APPROVE


def test_unknown_action_defaults_to_approval() -> None:
    d = _sentinel().evaluate(ToolCall(tool="?", action="frobnicate"))
    assert d.decision == Decision.QUEUE_APPROVAL  # default-deny → human


def test_lethal_trifecta_denied_even_when_approvable() -> None:
    # The classic indirect-injection exfiltration: untrusted page → read secret → send out.
    call = ToolCall(
        tool="email",
        action="send_email",  # normally APPROVE tier
        taints={Taint.UNTRUSTED, Taint.PRIVATE},
        has_private_access=True,
        has_egress=True,
        egress_domains=["evil.com"],
    )
    d = _sentinel().evaluate(call)
    assert d.decision == Decision.DENY
    assert "trifecta" in d.reason


def test_trifecta_not_triggered_without_untrusted() -> None:
    call = ToolCall(
        tool="email",
        action="send_email",
        taints={Taint.PRIVATE},  # no UNTRUSTED → not the trifecta
        has_private_access=True,
        has_egress=True,
        egress_domains=["example.com"],
    )
    d = _sentinel().evaluate(call)
    assert d.decision == Decision.QUEUE_APPROVAL  # falls through to approval


def test_auto_egress_blocked_when_not_allowlisted() -> None:
    call = ToolCall(
        tool="webhook", action="web_search", has_egress=True, egress_domains=["evil.com"]
    )
    d = _sentinel().evaluate(call)  # empty allowlist shipped
    assert d.decision == Decision.DENY


def test_auto_egress_allowed_when_allowlisted() -> None:
    call = ToolCall(
        tool="webhook", action="web_search", has_egress=True, egress_domains=["api.openai.com"]
    )
    d = _sentinel(egress_allowlist=["openai.com"]).evaluate(call)  # subdomain match
    assert d.decision == Decision.ALLOW


def test_kill_switch_denies_everything() -> None:
    s = Sentinel(_policy(), KillSwitch(engaged=True))
    d = s.evaluate(ToolCall(tool="search", action="web_search"))
    assert d.decision == Decision.DENY and "kill switch" in d.reason


def test_domain_allowed_helper() -> None:
    assert domain_allowed("api.openai.com", ["openai.com"])
    assert domain_allowed("openai.com", ["openai.com"])
    assert not domain_allowed("evil.com", ["openai.com"])
    assert not domain_allowed("notopenai.com", ["openai.com"])  # not a real subdomain


def test_secrets_broker_hides_raw_values() -> None:
    from midas.core.sentinel import SecretsBroker

    b = SecretsBroker()
    b.register("GMAIL_TOKEN", "super-secret-xyz")
    ref = b.reference("GMAIL_TOKEN")
    assert ref == "{{secret:GMAIL_TOKEN}}"
    assert "super-secret" not in ref  # the agent only ever holds the placeholder
    # resolution happens only at the trusted network boundary
    assert b.resolve(f"Bearer {ref}") == "Bearer super-secret-xyz"


def test_secrets_broker_unknown_handle_raises() -> None:
    import pytest

    from midas.core.sentinel import SecretsBroker

    with pytest.raises(KeyError):
        SecretsBroker().resolve("{{secret:MISSING}}")
