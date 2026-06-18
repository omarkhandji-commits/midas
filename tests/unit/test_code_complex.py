"""code.complex — delegate to local claude CLI, approval-gated.

The subprocess path is mocked. The point is to verify the policy logic:
prompt validation, workdir validation, timeout cap, env scrubbing, and
the drift-refusal at execute time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.code_complex import (
    CodeComplexError,
    _sha256,
    execute_code_complex,
    plan_code_complex,
)


def test_plan_rejects_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty prompt"):
        plan_code_complex(prompt="   ", workdir=str(tmp_path))


def test_plan_rejects_oversized_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="too large"):
        plan_code_complex(prompt="x" * 100_000, workdir=str(tmp_path))


def test_plan_rejects_relative_workdir() -> None:
    with pytest.raises(ValueError, match="absolute"):
        plan_code_complex(prompt="refactor x", workdir="./relative")


def test_plan_rejects_missing_workdir(tmp_path: Path) -> None:
    ghost = tmp_path / "ghost-dir-that-does-not-exist"
    with pytest.raises(ValueError, match="does not exist"):
        plan_code_complex(prompt="hi", workdir=str(ghost))


def test_plan_rejects_timeout_above_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout"):
        plan_code_complex(
            prompt="hi", workdir=str(tmp_path), timeout_seconds=99_999
        )


def test_plan_records_sha256(tmp_path: Path) -> None:
    plan = plan_code_complex(
        prompt="refactor login route", workdir=str(tmp_path), timeout_seconds=60
    )
    assert plan.sha256_prompt == _sha256("refactor login route")
    assert plan.timeout_seconds == 60
    assert plan.preview.startswith("refactor login")


def test_execute_refuses_prompt_drift(tmp_path: Path) -> None:
    payload = {
        "prompt": "tampered prompt now",
        "workdir": str(tmp_path),
        "timeout_seconds": 60,
        "sha256_prompt": _sha256("original safe prompt"),
    }
    with pytest.raises(CodeComplexError, match="prompt drifted"):
        execute_code_complex(payload)


def test_execute_refuses_when_cli_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `claude` is not on PATH we surface a clear install message."""
    monkeypatch.setattr(
        "midas.flagship.agent.tools.code_complex.find_claude_cli",
        lambda: None,
    )
    payload = {
        "prompt": "hi",
        "workdir": str(tmp_path),
        "timeout_seconds": 60,
        "sha256_prompt": _sha256("hi"),
    }
    with pytest.raises(CodeComplexError, match="not found on PATH"):
        execute_code_complex(payload)


def test_execute_scrubs_provider_keys_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subprocess must not see MIDAS provider keys.

    We capture the env that would have been passed by patching subprocess.run.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret-placeholder")
    monkeypatch.setenv("STRIPE_API_KEY", "stripe-secret-placeholder")
    monkeypatch.setenv("HOME", "/tmp/home")
    monkeypatch.setattr(
        "midas.flagship.agent.tools.code_complex.find_claude_cli",
        lambda: "/usr/bin/claude",
    )

    captured: dict[str, dict[str, str]] = {}

    class _FakeProc:
        returncode = 0
        stdout = '{"result": "ok", "cost_usd": 0.001}'
        stderr = ""

    def _fake_run(args, **kwargs):
        captured["env"] = kwargs.get("env") or {}
        return _FakeProc()

    monkeypatch.setattr(
        "midas.flagship.agent.tools.code_complex.subprocess.run", _fake_run
    )
    monkeypatch.setattr(
        "midas.flagship.agent.tools.code_complex._monotonic",
        lambda: 0.0,
    )

    payload = {
        "prompt": "hi",
        "workdir": str(tmp_path),
        "timeout_seconds": 60,
        "sha256_prompt": _sha256("hi"),
    }
    result = execute_code_complex(payload)
    env = captured["env"]
    assert "OPENAI_API_KEY" not in env
    assert "STRIPE_API_KEY" not in env
    assert env.get("HOME") == "/tmp/home"
    assert result.text == "ok"
    assert result.cost_usd == 0.001
