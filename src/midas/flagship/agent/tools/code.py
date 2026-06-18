"""Sandboxed code execution — the highest-risk tool, hard-gated.

`code.run` always maps to the policy action ``execute_code`` which lives in
``requires_approval``. The Sentinel parks every call in the approval queue; the
underlying subprocess only spawns from :func:`execute_code_approved`, which the
runtime calls after a human has resolved the approval.

Defense in depth on every approved execution:
- Python only in E1; the interpreter is the project's own ``sys.executable``.
- Subprocess CWD pinned to the workspace via :class:`FsGuard`.
- Environment scrubbed: only PATH (when present) and a few benign variables survive.
  HTTP/HTTPS/ALL proxy vars are forced to an invalid loopback sink to make
  off-the-shelf network libraries fail fast.
- Wall-clock timeout (default 10 s, configurable, hard upper bound 60 s).
- stdout + stderr are read with a byte cap; output past the cap is truncated.
- The user code is wrapped in a prelude that monkey-patches ``socket.socket`` to
  raise immediately — covers the common case. We do NOT claim this is a full
  sandbox; the real security boundary is the APPROVE-tier human review.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path

from .fsguard import FsGuard

_MAX_OUTPUT_BYTES = 64_000
_TIMEOUT_HARD_CAP = 60.0

_NETWORK_BLOCK_PRELUDE = """\
import socket as _socket
def _midas_no_network(*a, **k):
    raise PermissionError("network access blocked by MIDAS code.run sandbox")
_socket.socket = _midas_no_network  # type: ignore[assignment]
try:
    import urllib.request as _u
    _u.urlopen = _midas_no_network  # type: ignore[assignment]
except Exception:
    pass
"""


@dataclass(frozen=True)
class CodePlan:
    """Payload of an `execute_code` approval. The code lives here until approved."""

    code: str
    language: str
    timeout_seconds: float
    code_sha256: str
    preview: str


@dataclass(frozen=True)
class CodeRunResult:
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool
    timed_out: bool
    duration_seconds: float
    # WS6 — additive: label which isolation tier actually executed the code.
    # Defaults to "process" (the historical behaviour). Existing callers and
    # serialized outputs unaffected.
    isolation: str = "process"


def plan_code_run(code: str, *, language: str = "python", timeout: float = 10.0) -> CodePlan:
    """Build the approval payload. Does NOT execute."""
    if language != "python":
        raise ValueError(f"unsupported language: {language!r} (python only in E1)")
    timeout = max(0.1, min(float(timeout), _TIMEOUT_HARD_CAP))
    import hashlib

    digest = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()
    return CodePlan(
        code=code,
        language=language,
        timeout_seconds=timeout,
        code_sha256=digest,
        preview=code[:400],
    )


def execute_code_approved(
    guard: FsGuard,
    plan: CodePlan,
    *,
    python_executable: str | None = None,
    mode: str = "auto",
) -> CodeRunResult:
    """Run an APPROVED code plan in the workspace sandbox. Caller guarantees approval.

    WS6 — ``mode``:
    - ``"process"`` (legacy default behaviour): subprocess with -I -S, scrubbed env,
      socket monkey-patch, poisoned proxies. Available everywhere.
    - ``"container"``: rootless ``podman``/``docker`` with ``--net=none`` and
      dropped capabilities. Returns an error result with isolation="unavailable"
      if no container runtime is found on PATH.
    - ``"auto"`` (default for new calls): try container, fall back to process if
      the runtime is missing. Either way the CodeRunResult.isolation field
      records what actually ran.
    """
    import time

    workspace = guard.workspace
    workspace.mkdir(parents=True, exist_ok=True)

    # Container path (opt-in / auto-detected).
    if mode in ("container", "auto"):
        runtime = _detect_container_runtime()
        if runtime is not None:
            return _run_in_container(runtime, workspace, plan)
        if mode == "container":
            # Explicit request, no runtime: refuse rather than silently downgrade.
            return CodeRunResult(
                exit_code=127,
                stdout="",
                stderr="container mode requested but no podman/docker on PATH",
                truncated=False,
                timed_out=False,
                duration_seconds=0.0,
                isolation="unavailable",
            )
        # mode == "auto" and no container → fall through to process.

    return _run_in_process(workspace, plan, python_executable, t0=time.monotonic())


def _run_in_process(
    workspace: Path,
    plan: CodePlan,
    python_executable: str | None,
    *,
    t0: float,
) -> CodeRunResult:
    """Process-level sandbox — historical behaviour, unchanged."""
    import time

    wrapped = _NETWORK_BLOCK_PRELUDE + "\n" + plan.code
    env = _scrubbed_env()
    interpreter = python_executable or sys.executable

    args = [interpreter, "-I", "-S", "-c", wrapped]
    timed_out = False
    truncated = False
    try:
        proc = subprocess.run(  # nosec B603
            args,
            cwd=str(workspace),
            env=env,
            capture_output=True,
            timeout=plan.timeout_seconds,
            check=False,
        )
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = 124
    except (OSError, subprocess.SubprocessError) as exc:
        return CodeRunResult(
            exit_code=126,
            stdout="",
            stderr=f"sandbox failed to launch: {exc}",
            truncated=False,
            timed_out=False,
            duration_seconds=time.monotonic() - t0,
            isolation="process",
        )

    if len(stdout) > _MAX_OUTPUT_BYTES:
        truncated = True
        stdout = stdout[:_MAX_OUTPUT_BYTES]
    if len(stderr) > _MAX_OUTPUT_BYTES:
        truncated = True
        stderr = stderr[:_MAX_OUTPUT_BYTES]

    return CodeRunResult(
        exit_code=exit_code,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        truncated=truncated,
        timed_out=timed_out,
        duration_seconds=round(time.monotonic() - t0, 4),
        isolation="process",
    )


def _detect_container_runtime() -> str | None:
    """Return ``"podman"`` or ``"docker"`` if available on PATH, else None."""
    import shutil

    for name in ("podman", "docker"):
        if shutil.which(name) is not None:
            return name
    return None


def _run_in_container(runtime: str, workspace: Path, plan: CodePlan) -> CodeRunResult:
    """Run inside a rootless container with --net=none.

    Best-effort: returns an error result if launching the container fails. We do
    NOT auto-pull an image — the operator pre-pulls ``python:3.11-slim`` (or sets
    ``MIDAS_SANDBOX_IMAGE``) before running. This keeps the surface auditable.
    """
    import os
    import time

    image = os.environ.get("MIDAS_SANDBOX_IMAGE", "python:3.11-slim")
    wrapped = _NETWORK_BLOCK_PRELUDE + "\n" + plan.code
    cmd = [
        runtime, "run", "--rm",
        "--net=none",
        "--cap-drop=ALL",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",  # nosec B108
        "-v", f"{str(workspace)}:/work:rw",
        "-w", "/work",
        image,
        "python", "-I", "-S", "-c", wrapped,
    ]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(  # nosec B603
            cmd, capture_output=True, timeout=plan.timeout_seconds, check=False,
        )
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = int(proc.returncode)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = 124
        timed_out = True
    except (OSError, subprocess.SubprocessError) as exc:
        return CodeRunResult(
            exit_code=126,
            stdout="",
            stderr=f"container sandbox failed to launch: {exc}",
            truncated=False,
            timed_out=False,
            duration_seconds=time.monotonic() - t0,
            isolation="container-failed",
        )

    truncated = False
    if len(stdout) > _MAX_OUTPUT_BYTES:
        truncated = True
        stdout = stdout[:_MAX_OUTPUT_BYTES]
    if len(stderr) > _MAX_OUTPUT_BYTES:
        truncated = True
        stderr = stderr[:_MAX_OUTPUT_BYTES]

    return CodeRunResult(
        exit_code=exit_code,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        truncated=truncated,
        timed_out=timed_out,
        duration_seconds=round(time.monotonic() - t0, 4),
        isolation="container",
    )


def _scrubbed_env() -> dict[str, str]:
    """A minimal env: only PATH + locale + a poisoned proxy so accidental HTTP fails."""
    import os

    base: dict[str, str] = {}
    for k in ("PATH", "SystemRoot", "WINDIR", "LANG", "LC_ALL", "TMP", "TEMP"):
        v = os.environ.get(k)
        if v:
            base[k] = v
    # Make stdlib network libs fail fast if the prelude monkey-patch is bypassed:
    base["HTTP_PROXY"] = "http://127.0.0.1:1"
    base["HTTPS_PROXY"] = "http://127.0.0.1:1"
    base["ALL_PROXY"] = "http://127.0.0.1:1"
    base["NO_PROXY"] = ""
    # Belt and suspenders: no inherited PYTHONPATH/PYTHONHOME.
    return base


def workspace_root(guard: FsGuard) -> Path:
    return guard.workspace
