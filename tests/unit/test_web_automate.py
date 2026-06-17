"""web.automate — schema, hash, password-shaped refusal, drift refusal."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.web_automate import (
    AutomateError,
    _canonical,
    _sha256,
    execute_web_automate,
    plan_web_automate,
)


def test_plan_rejects_relative_url() -> None:
    with pytest.raises(ValueError, match="absolute http"):
        plan_web_automate(
            start_url="/foo",
            actions=[{"kind": "click", "selector": "button"}],
        )


def test_plan_rejects_empty_actions() -> None:
    with pytest.raises(ValueError, match="at least one action"):
        plan_web_automate(start_url="https://example.com", actions=[])


def test_plan_rejects_unknown_action_kind() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        plan_web_automate(
            start_url="https://example.com",
            actions=[{"kind": "evaluate", "code": "alert(1)"}],
        )


def test_plan_rejects_overlong_sequence() -> None:
    long = [{"kind": "wait", "ms": 100} for _ in range(30)]
    with pytest.raises(ValueError, match="too long"):
        plan_web_automate(start_url="https://example.com", actions=long)


def test_plan_rejects_password_shaped_selector() -> None:
    """If the planner tries to type into a password field, refuse — wire a
    credential vault instead of leaving the secret in an approval payload."""
    with pytest.raises(ValueError, match="password-shaped"):
        plan_web_automate(
            start_url="https://example.com/login",
            actions=[
                {"kind": "fill", "selector": "#password", "value": "hunter2"},
            ],
        )


def test_plan_rejects_fill_without_value() -> None:
    with pytest.raises(ValueError, match="non-empty value"):
        plan_web_automate(
            start_url="https://example.com",
            actions=[{"kind": "fill", "selector": "#email", "value": ""}],
        )


def test_plan_rejects_overlong_wait() -> None:
    with pytest.raises(ValueError, match="ms in"):
        plan_web_automate(
            start_url="https://example.com",
            actions=[{"kind": "wait", "ms": 60_000}],
        )


def test_plan_records_canonical_hash() -> None:
    actions = [
        {"kind": "click", "selector": "button#search"},
        {"kind": "fill", "selector": "input[name=q]", "value": "bakery"},
    ]
    plan = plan_web_automate(start_url="https://x.com", actions=actions)
    assert plan.sha256_actions == _sha256(_canonical(plan.actions))
    assert plan.preview.startswith("start: https://x.com")


def test_execute_refuses_action_drift() -> None:
    """Tamper with the action list between approval and execute — must refuse."""
    original = [{"kind": "click", "selector": "#a"}]
    payload = {
        "start_url": "https://example.com",
        "actions": [{"kind": "click", "selector": "#tampered"}],
        "timeout_seconds": 30,
        "allow_disallowed_robots": True,
        "sha256_actions": _sha256(_canonical(original)),
    }
    with pytest.raises(AutomateError, match="action list drifted"):
        execute_web_automate(payload)


def test_execute_refuses_missing_required_fields() -> None:
    with pytest.raises(AutomateError, match="missing"):
        execute_web_automate({"start_url": "", "actions": []})
