"""code.complex — delegate heavy coding tasks to a local Claude Code CLI.

Why
---
MIDAS's own ``code.run`` (sandboxed python execution) covers fast,
deterministic snippets. Real refactors, multi-file edits, codebase
exploration — that's what Claude Code does well. Rather than reimplement
that engine, ``code.complex`` shells out to the operator's already-authed
``claude`` CLI, captures the result, and records a receipt.

Contract
--------
- Plan validates the prompt + workdir, NO subprocess starts.
- The approval payload carries the prompt + sha256 + bounded timeout.
- Executor runs ``claude -p "<prompt>" --output-format json`` in the
  approved workdir, captures stdout, parses the JSON result, returns the
  text + cost + duration in a clean shape.
- Action: ``execute_code`` (already APPROVE-tier in default policy).
- No egress from the planner side; the CLI handles its own auth + egress.

Honest constraints
------------------
- We do NOT fall back to ``code.run`` on failure. A failed sub-agent
  records a DENY receipt; the operator decides what's next.
- We do NOT pass the operator's MIDAS keys to the subprocess. Claude Code
  has its own auth — keeping them separate is part of the safety envelope.
- We do NOT auto-approve diffs returned by the subagent. Anything that
  touches the filesystem still goes through MIDAS's own ``fs.write``
  approval flow.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CodeComplexError(RuntimeError):
    """Raised when code.complex can't satisfy the request."""


@dataclass
class CodeComplexPlan:
    """Approval payload — describes the delegation, not its output."""

    kind: str  # always "code_complex"
    prompt: str
    workdir: str
    timeout_seconds: float
    sha256_prompt: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CodeComplexResult:
    """Flat shape recorded in the executed receipt."""

    text: str
    cost_usd: float
    duration_seconds: float
    exit_code: int
    truncated: bool


_MAX_PROMPT_CHARS = 50_000
_MAX_OUTPUT_CHARS = 100_000
_DEFAULT_TIMEOUT = 300.0  # 5 minutes — sub-agent runs can take longer than code.run
_MAX_TIMEOUT = 1_800.0   # 30-minute ceiling regardless of caller


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def plan_code_complex(
    *,
    prompt: str,
    workdir: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT,
) -> CodeComplexPlan:
    """Build the approval payload. No subprocess runs here."""
    if not prompt.strip():
        raise ValueError("code.complex needs a non-empty prompt")
    if len(prompt) > _MAX_PROMPT_CHARS:
        raise ValueError(
            f"code.complex prompt is too large "
            f"({len(prompt)} > {_MAX_PROMPT_CHARS}); split the task"
        )
    if not workdir.strip():
        raise ValueError("code.complex needs an absolute workdir")
    wd = Path(workdir).expanduser()
    if not wd.is_absolute():
        raise ValueError(
            f"code.complex workdir must be absolute, got {workdir!r}"
        )
    if not wd.exists() or not wd.is_dir():
        raise ValueError(
            f"code.complex workdir does not exist or is not a directory: {workdir!r}"
        )
    timeout = float(timeout_seconds)
    if timeout <= 0 or timeout > _MAX_TIMEOUT:
        raise ValueError(
            f"code.complex timeout must be in (0, {_MAX_TIMEOUT}], got {timeout}"
        )
    return CodeComplexPlan(
        kind="code_complex",
        prompt=prompt.strip(),
        workdir=str(wd.resolve()),
        timeout_seconds=timeout,
        sha256_prompt=_sha256(prompt.strip()),
        preview=prompt.strip()[:400],
        meta={"prompt_chars": len(prompt)},
    )


def find_claude_cli() -> str | None:
    """Locate the `claude` CLI on PATH. None if not installed."""
    return shutil.which("claude")


def execute_code_complex(payload: dict[str, Any]) -> CodeComplexResult:
    """Post-approval executor. Spawns ``claude`` and parses its JSON output.

    Raises :class:`CodeComplexError` for: missing CLI, payload tampering,
    subprocess timeout, malformed CLI output.
    """
    prompt = str(payload.get("prompt") or "")
    workdir = str(payload.get("workdir") or "")
    timeout = float(payload.get("timeout_seconds") or _DEFAULT_TIMEOUT)
    if not prompt or not workdir:
        raise CodeComplexError("payload missing prompt or workdir")
    expected = str(payload.get("sha256_prompt") or "")
    if expected and _sha256(prompt) != expected:
        raise CodeComplexError(
            "code.complex refused: payload prompt drifted from approval"
        )

    cli = find_claude_cli()
    if cli is None:
        raise CodeComplexError(
            "claude CLI not found on PATH; install Claude Code first "
            "(https://claude.com/claude-code)"
        )

    # Run in a clean env subset — never leak MIDAS's LLM provider keys to
    # the subagent. The CLI uses its own auth.
    safe_env = {
        k: v for k, v in os.environ.items()
        if k.upper()
        not in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
            "GROQ_API_KEY",
            "GOOGLE_API_KEY",
            "STRIPE_API_KEY",
            "STRIPE_WEBHOOK_SECRET",
        }
    }

    started = _monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 — we control args and cwd
            [cli, "-p", prompt, "--output-format", "json"],
            cwd=workdir,
            env=safe_env,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise CodeComplexError(
            f"claude CLI timed out after {timeout}s"
        ) from e
    except (OSError, FileNotFoundError) as e:
        raise CodeComplexError(f"claude CLI failed to start: {e}") from e
    elapsed = _monotonic() - started

    if proc.returncode != 0:
        # Surface stderr to the operator (claude CLI writes errors there);
        # truncate to avoid huge logs.
        raise CodeComplexError(
            f"claude CLI exited with {proc.returncode}: "
            f"{(proc.stderr or '')[:500]}"
        )

    # Parse the JSON output. Claude Code emits a structured result with
    # at minimum 'result' (text) and a 'cost_usd' field as of 2025.
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise CodeComplexError(
            f"claude CLI returned non-JSON output: {e}"
        ) from e
    text = str(parsed.get("result") or "")
    cost = float(parsed.get("cost_usd") or parsed.get("total_cost_usd") or 0.0)
    truncated = len(text) > _MAX_OUTPUT_CHARS
    return CodeComplexResult(
        text=text[:_MAX_OUTPUT_CHARS],
        cost_usd=cost,
        duration_seconds=round(elapsed, 3),
        exit_code=proc.returncode,
        truncated=truncated,
    )


def _monotonic() -> float:
    """Indirected for tests."""
    import time

    return time.monotonic()
