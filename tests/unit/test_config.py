"""Config loader: the shipped policy.yml / providers.example.yml parse into typed models."""

from __future__ import annotations

from pathlib import Path

from midas.core.config import Autonomy, load_app_config, load_policy, load_providers

BASE = Path(__file__).resolve().parents[2]  # midas/


def test_policy_parses_from_shipped_file() -> None:
    policy = load_policy(BASE / "config" / "policy.yml")
    assert policy.autonomy == Autonomy.SEMI_AUTO  # approval-default (locked)
    assert policy.spend_caps.per_task == 0.25
    assert policy.spend_caps.daily == 2.0
    assert policy.spend_caps.monthly == 30.0
    # the "never" list is the hard-forbidden set the Sentinel enforces
    assert "spam" in policy.actions.never
    assert "leak_secret" in policy.actions.never
    # outbound actions require approval
    assert "send_email" in policy.actions.requires_approval
    assert "web_search" in policy.actions.allowed_without_approval
    # egress is deny-by-default (empty allowlist shipped)
    assert policy.egress_allowlist == []


def test_providers_parse_from_example() -> None:
    providers = load_providers(BASE / "config" / "providers.example.yml")
    assert "cheap" in providers.roles
    assert "smart" in providers.roles
    assert providers.roles["cheap"].primary  # non-empty
    assert providers.routing.default_role == "cheap"


def test_app_config_caps_and_autonomy() -> None:
    cfg = load_app_config(BASE)
    per_task, daily, monthly = cfg.caps()
    assert (per_task, daily, monthly) == (0.25, 2.0, 30.0)
    assert cfg.autonomy == Autonomy.SEMI_AUTO
    assert cfg.kill_switch is False
