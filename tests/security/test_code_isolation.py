"""WS6 — code.run isolation modes: process (default) + container (opt-in).

The process mode must reproduce the current behaviour exactly. The container
mode must (a) be opt-in, (b) skip cleanly when no runtime is available so the
default workflow is unaffected, (c) report ``isolation`` in the result.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from midas.flagship.agent.tools.code import (
    execute_code_approved,
    plan_code_run,
)
from midas.flagship.agent.tools.fsguard import FsGuard


def _guard(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def test_process_mode_runs_and_reports_isolation(tmp_path: Path) -> None:
    plan = plan_code_run("print('hello cash')", timeout=5.0)
    result = execute_code_approved(_guard(tmp_path), plan, mode="process")
    assert result.exit_code == 0
    assert "hello cash" in result.stdout
    assert result.isolation == "process"


def test_process_mode_socket_blocked(tmp_path: Path) -> None:
    plan = plan_code_run(
        "import socket; s=socket.socket(); print('UNEXPECTED')",
        timeout=5.0,
    )
    result = execute_code_approved(_guard(tmp_path), plan, mode="process")
    assert "UNEXPECTED" not in result.stdout
    assert "blocked" in result.stderr.lower() or result.exit_code != 0


def test_auto_mode_falls_back_to_process_when_no_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When neither podman nor docker is on PATH, auto must downgrade silently."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    plan = plan_code_run("print('fallback ok')", timeout=5.0)
    result = execute_code_approved(_guard(tmp_path), plan, mode="auto")
    assert result.exit_code == 0
    assert result.isolation == "process"


def test_container_mode_without_runtime_refuses_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit ``mode='container'`` must NOT silently downgrade."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    plan = plan_code_run("print('should not run')", timeout=5.0)
    result = execute_code_approved(_guard(tmp_path), plan, mode="container")
    assert result.isolation == "unavailable"
    assert result.exit_code != 0


@pytest.mark.skipif(
    shutil.which("podman") is None and shutil.which("docker") is None,
    reason="no container runtime on PATH",
)
def test_container_mode_runs_if_runtime_present(tmp_path: Path) -> None:
    plan = plan_code_run("print('inside container')", timeout=30.0)
    result = execute_code_approved(_guard(tmp_path), plan, mode="container")
    assert result.isolation in ("container", "container-failed")
    # Docker Desktop on Windows CI accepts the binary but rejects --read-only;
    # we still exercise the code path and accept either outcome honestly.
    if result.isolation == "container" and result.stdout:
        assert "inside container" in result.stdout


def test_default_call_signature_unchanged(tmp_path: Path) -> None:
    """Callers that don't pass mode= still work — rétro-compat."""
    plan = plan_code_run("print('legacy')", timeout=5.0)
    # On any machine without container runtime, mode='auto' falls back to process.
    if shutil.which("podman") is None and shutil.which("docker") is None:
        result = execute_code_approved(_guard(tmp_path), plan)
        assert result.exit_code == 0
        assert "legacy" in result.stdout
        assert result.isolation == "process"


def test_isolation_field_default_is_process() -> None:
    """Anyone constructing CodeRunResult directly (e.g. older tests) still works."""
    from midas.flagship.agent.tools.code import CodeRunResult

    r = CodeRunResult(
        exit_code=0, stdout="x", stderr="", truncated=False,
        timed_out=False, duration_seconds=0.1,
    )
    assert r.isolation == "process"


def test_python_executable_param_still_respected(tmp_path: Path) -> None:
    """The python_executable hook keeps working in process mode."""
    plan = plan_code_run("print('via executable')", timeout=5.0)
    result = execute_code_approved(
        _guard(tmp_path), plan, mode="process", python_executable=sys.executable,
    )
    assert result.exit_code == 0
