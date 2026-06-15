"""Filesystem chokepoint — the ONLY way agent tools resolve a path.

`policy.filesystem` is declared in config/policy.yml but, until Stream E, was not
enforced by any code path. This module is that enforcement. Every tool that reads,
writes, lists, or executes anything against a filesystem path resolves it through
:meth:`FsGuard.resolve` first. The guard:

- canonicalizes the path against a fixed workspace root,
- refuses anything that escapes the workspace via ``..`` or absolute paths,
- refuses symlinks that point outside the workspace,
- refuses any prefix listed in ``policy.filesystem.deny_paths``,
- is adversarially tested (see ``tests/security/test_fsguard.py``).

Cross-platform: works on Windows + POSIX. On Windows the deny list normally contains
backslash paths; we canonicalize both sides to forward slashes for the prefix check.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class FsGuardError(PermissionError):
    """Raised when a path violates the workspace sandbox."""


def _norm(p: Path) -> str:
    # Compare on resolved, forward-slashed strings so Windows + POSIX match.
    return str(p).replace("\\", "/").rstrip("/")


@dataclass(frozen=True)
class FsGuard:
    """Resolve and check a filesystem path against the workspace + deny list."""

    workspace: Path
    deny_paths: tuple[str, ...] = ()
    workspace_only: bool = True

    @classmethod
    def from_policy(cls, workspace: str | Path, policy_filesystem: object) -> FsGuard:
        """Build a guard from policy.filesystem (which is a Pydantic model or dict-like).

        Tolerates either a Pydantic model with attributes or a plain dict, so a
        future policy refactor doesn't break this chokepoint.
        """
        workspace_path = Path(workspace).resolve()
        deny: Iterable[str] = ()
        workspace_only = True
        if hasattr(policy_filesystem, "deny_paths"):
            deny = getattr(policy_filesystem, "deny_paths", ()) or ()
            workspace_only = bool(getattr(policy_filesystem, "workspace_only", True))
        elif isinstance(policy_filesystem, dict):
            deny = policy_filesystem.get("deny_paths") or ()
            workspace_only = bool(policy_filesystem.get("workspace_only", True))
        return cls(
            workspace=workspace_path,
            deny_paths=tuple(_expand(d) for d in deny),
            workspace_only=workspace_only,
        )

    def resolve(self, path: str | Path, *, must_exist: bool = False) -> Path:
        """Canonicalize ``path`` and refuse anything outside the workspace/deny list.

        - Empty paths, absolute paths outside the workspace, and ``..`` escapes raise.
        - Symlinks: the resolved target must also be inside the workspace.
        - ``must_exist=True`` raises FsGuardError instead of FileNotFoundError when
          the path doesn't exist, so callers can centralize the error type.
        """
        raw = str(path or "").strip()
        if not raw:
            raise FsGuardError("empty path")

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate

        # `resolve(strict=False)` collapses .. without requiring existence; we then
        # re-check the resolved string against the workspace and the deny list.
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as exc:  # symlink loop, etc.
            raise FsGuardError(f"cannot resolve path: {raw}") from exc

        resolved_norm = _norm(resolved)
        workspace_norm = _norm(self.workspace)

        if self.workspace_only and not (
            resolved_norm == workspace_norm
            or resolved_norm.startswith(workspace_norm + "/")
        ):
            raise FsGuardError(
                f"path escapes the workspace sandbox: {raw} → {resolved}"
            )

        for denied in self.deny_paths:
            denied_norm = _norm(Path(denied))
            if not denied_norm:
                continue
            if resolved_norm == denied_norm or resolved_norm.startswith(denied_norm + "/"):
                raise FsGuardError(f"path is on the deny-list ({denied}): {raw}")

        # Reject symlinks whose REAL target escapes — even if the link itself is
        # inside the workspace.
        if resolved.is_symlink():
            try:
                target = resolved.readlink()
            except OSError as exc:
                raise FsGuardError(f"cannot read symlink target: {raw}") from exc
            target_abs = (resolved.parent / target).resolve(strict=False)
            target_norm = _norm(target_abs)
            if self.workspace_only and not (
                target_norm == workspace_norm
                or target_norm.startswith(workspace_norm + "/")
            ):
                raise FsGuardError(f"symlink target escapes workspace: {raw} → {target}")

        if must_exist and not resolved.exists():
            raise FsGuardError(f"path does not exist: {raw}")

        return resolved


def _expand(value: str) -> str:
    """Expand ~ and env vars in a deny-list entry so the guard matches reality."""
    return os.path.expanduser(os.path.expandvars(value))
