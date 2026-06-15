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

import subprocess  # nosec B404 - guarded execution, see module docstring
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
) -> CodeRunResult:
    """Run an APPROVED code plan in the workspace sandbox. Caller guarantees approval."""
    import time

    workspace = guard.workspace
    workspace.mkdir(parents=True, exist_ok=True)

    wrapped = _NETWORK_BLOCK_PRELUDE + "\n" + plan.code
    env = _scrubbed_env()
    interpreter = python_executable or sys.executable

    args = [interpreter, "-I", "-S", "-c", wrapped]
    start = time.monotonic()
    timed_out = False
    truncated = False
    try:
        proc = subprocess.run(  # nosec B603 - args are not shell-interpreted; CWD + env scrubbed
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
        exit_code = 124  # POSIX convention for timeout
    except (OSError, subprocess.SubprocessError) as exc:
        return CodeRunResult(
            exit_code=126,
            stdout="",
            stderr=f"sandbox failed to launch: {exc}",
            truncated=False,
            timed_out=False,
            duration_seconds=time.monotonic() - start,
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
        duration_seconds=round(time.monotonic() - start, 4),
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
