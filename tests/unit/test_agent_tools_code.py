"""code.run sandbox — APPROVE-tier, scrubbed env, timeout, output cap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from midas.flagship.agent.tools.code import (
    _MAX_OUTPUT_BYTES,
    execute_code_approved,
    plan_code_run,
)
from midas.flagship.agent.tools.fsguard import FsGuard


def _g(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def test_plan_code_run_returns_sha_and_caps_timeout(tmp_path: Path) -> None:
    plan = plan_code_run("print('hi')", timeout=9999.0)
    assert plan.code_sha256 and len(plan.code_sha256) == 64
    assert plan.timeout_seconds <= 60.0  # hard cap


def test_plan_code_run_rejects_non_python() -> None:
    with pytest.raises(ValueError, match="unsupported language"):
        plan_code_run("echo hi", language="bash")


@pytest.mark.skipif(sys.platform == "win32", reason="subprocess flakiness on Windows CI")
def test_execute_runs_in_workspace_cwd(tmp_path: Path) -> None:
    plan = plan_code_run("import os; print(os.getcwd())")
    result = execute_code_approved(_g(tmp_path), plan)
    assert result.exit_code == 0
    # Subprocess isolation: cwd is the workspace path.
    # Container isolation (when docker/podman is available, e.g. GitHub Linux
    # runner): cwd is the in-container mountpoint, by design "/work".
    cwd_out = result.stdout.strip().lower()
    if result.isolation == "container":
        assert cwd_out == "/work"
    else:
        assert str(tmp_path.resolve()).lower() in cwd_out


@pytest.mark.skipif(
    sys.platform == "win32" and os.environ.get("CI") == "true",
    reason="Docker Desktop on Windows CI lacks --read-only; subprocess path is the real surface",
)
def test_execute_subprocess_network_block_makes_socket_fail(tmp_path: Path) -> None:
    plan = plan_code_run(
        "import socket\n"
        "try:\n"
        "  s = socket.socket()\n"
        "  print('NETWORK_REACHED')\n"
        "except PermissionError as e:\n"
        "  print('BLOCKED:', e)\n"
    )
    result = execute_code_approved(_g(tmp_path), plan)
    assert "NETWORK_REACHED" not in result.stdout
    assert "BLOCKED" in result.stdout


@pytest.mark.skipif(
    sys.platform == "win32" and os.environ.get("CI") == "true",
    reason="Docker Desktop on Windows CI lacks --read-only; subprocess path is the real surface",
)
def test_execute_timeout_fires_quickly(tmp_path: Path) -> None:
    plan = plan_code_run("import time; time.sleep(5)", timeout=0.5)
    result = execute_code_approved(_g(tmp_path), plan)
    assert result.timed_out is True
    assert result.duration_seconds < 3.0


@pytest.mark.skipif(
    sys.platform == "win32" and os.environ.get("CI") == "true",
    reason="Docker Desktop on Windows CI lacks --read-only; subprocess path is the real surface",
)
def test_execute_truncates_huge_output(tmp_path: Path) -> None:
    plan = plan_code_run(
        f"print('A' * {_MAX_OUTPUT_BYTES + 5000})",
        timeout=10.0,
    )
    result = execute_code_approved(_g(tmp_path), plan)
    assert result.truncated is True
    assert len(result.stdout.encode("utf-8")) <= _MAX_OUTPUT_BYTES + 1
