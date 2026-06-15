"""Adversarial fsguard tests — the workspace chokepoint must hold.

If any of these fails, MIDAS can be tricked into reading/writing outside the
workspace. Treat as a release gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from midas.flagship.agent.tools.fsguard import FsGuard, FsGuardError


def _guard(tmp_path: Path) -> FsGuard:
    deny = ["C:\\Windows", "/etc", "/usr"]
    return FsGuard(workspace=tmp_path.resolve(), deny_paths=tuple(deny), workspace_only=True)


def test_resolves_relative_path_inside_workspace(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    resolved = g.resolve("a.txt", must_exist=True)
    assert resolved == (tmp_path / "a.txt").resolve()


def test_rejects_dotdot_escape(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    with pytest.raises(FsGuardError, match="escape"):
        g.resolve("../../etc/passwd")


def test_rejects_absolute_outside_workspace(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    outside = (tmp_path.parent / "outside.txt")
    with pytest.raises(FsGuardError, match="escape"):
        g.resolve(str(outside))


def test_rejects_deny_path_prefix(tmp_path: Path) -> None:
    # Build a guard whose workspace IS the deny path's parent so a hit is achievable
    # without violating workspace_only.
    workspace = tmp_path.resolve()
    deny = str(workspace / "secret")
    g = FsGuard(workspace=workspace, deny_paths=(deny,), workspace_only=True)
    (workspace / "secret").mkdir()
    (workspace / "secret" / "x.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(FsGuardError, match="deny-list"):
        g.resolve("secret/x.txt")


def test_empty_path_rejected(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    with pytest.raises(FsGuardError, match="empty"):
        g.resolve("")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require admin on Windows")
def test_rejects_symlink_target_outside_workspace(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(FsGuardError, match="symlink target escapes"):
        g.resolve("link.txt")


def test_must_exist_raises_fsguard_error_not_filenotfound(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    with pytest.raises(FsGuardError, match="does not exist"):
        g.resolve("nope.txt", must_exist=True)


def test_workspace_root_itself_resolves(tmp_path: Path) -> None:
    g = _guard(tmp_path)
    assert g.resolve(".") == tmp_path.resolve()


def test_from_policy_accepts_pydantic_or_dict(tmp_path: Path) -> None:
    g1 = FsGuard.from_policy(
        tmp_path, {"workspace_only": True, "deny_paths": [str(tmp_path / "x")]}
    )
    assert g1.workspace == tmp_path.resolve()
    assert g1.deny_paths == (str(tmp_path / "x"),)

    class _FakePolicy:
        workspace_only = True
        deny_paths = [str(tmp_path / "y")]

    g2 = FsGuard.from_policy(tmp_path, _FakePolicy())
    assert g2.deny_paths == (str(tmp_path / "y"),)
