"""Filesystem tools — read, list, and gated write.

Every entry point passes through :class:`FsGuard` first. ``fs.read`` and ``fs.list``
are AUTO (mapped to ``read_local_files``). ``fs.write`` is APPROVE (mapped to
``repo_write``) — the callable never runs inline, the toolset parks it in the
approval queue and a separate execute step (`execute_fs_write`) writes the bytes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .fsguard import FsGuard


@dataclass(frozen=True)
class FsReadResult:
    path: str
    size_bytes: int
    sha256: str
    text: str  # truncated to max_chars


@dataclass(frozen=True)
class FsListResult:
    path: str
    entries: list[str]


@dataclass(frozen=True)
class FsWritePlan:
    """The payload of a gated fs.write approval. The bytes live here until approved."""

    path: str
    bytes_len: int
    sha256_new: str
    sha256_prev: str | None  # None when the target doesn't exist yet
    preview: str  # first ~400 chars when textual, else "(binary)"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fs_read(guard: FsGuard, path: str, *, max_chars: int = 100_000) -> FsReadResult:
    target = guard.resolve(path, must_exist=True)
    raw = target.read_bytes()
    try:
        text = raw.decode("utf-8", errors="replace")[:max_chars]
    except UnicodeDecodeError:
        text = ""
    return FsReadResult(
        path=str(target),
        size_bytes=len(raw),
        sha256=_sha256_hex(raw),
        text=text,
    )


def fs_list(guard: FsGuard, path: str = ".") -> FsListResult:
    target = guard.resolve(path, must_exist=True)
    if not target.is_dir():
        raise NotADirectoryError(f"not a directory: {target}")
    entries = sorted(p.name for p in target.iterdir())
    return FsListResult(path=str(target), entries=entries)


def plan_fs_write(guard: FsGuard, path: str, content: str | bytes) -> FsWritePlan:
    """Build the approval-payload for an fs.write. Does NOT write."""
    target = guard.resolve(path)
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    sha_prev: str | None = None
    if target.exists() and target.is_file():
        sha_prev = _sha256_hex(target.read_bytes())
    preview = "(binary)"
    if isinstance(content, str):
        preview = content[:400]
    else:
        try:
            preview = data[:400].decode("utf-8")
        except UnicodeDecodeError:
            pass
    return FsWritePlan(
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256_hex(data),
        sha256_prev=sha_prev,
        preview=preview,
    )


def execute_fs_write(guard: FsGuard, path: str, content: str | bytes) -> FsWritePlan:
    """Actually write the file. Caller MUST verify the approval is resolved first.

    Returns a finalized plan that mirrors what the approval card promised, so the
    receipt of the executed write can be compared with the approval's payload.
    """
    target = guard.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    sha_prev: str | None = None
    if target.exists() and target.is_file():
        sha_prev = _sha256_hex(target.read_bytes())
    target.write_bytes(data)
    return FsWritePlan(
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256_hex(data),
        sha256_prev=sha_prev,
        preview=_preview(content),
    )


def _preview(content: str | bytes) -> str:
    if isinstance(content, str):
        return content[:400]
    try:
        return bytes(content)[:400].decode("utf-8")
    except UnicodeDecodeError:
        return "(binary)"


def is_inside_workspace(guard: FsGuard, target: Path) -> bool:
    """Convenience for callers that need a yes/no without raising."""
    try:
        guard.resolve(target)
    except PermissionError:
        return False
    return True
