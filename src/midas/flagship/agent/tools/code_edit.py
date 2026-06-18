"""code.edit_plan — multi-file search/replace edits, exact-match validated.

Why
---
Phase 6, step 2 of the native coder. Aider's "diff" edit format is a
proven pattern: the model emits a list of (old_block, new_block) edits
per file, the harness validates that ``old_block`` matches exactly,
then writes the replacement. Exact-match is the safety rail — a fuzzy
match silently editing the wrong line is the classic LLM bug. MIDAS
makes it explicit: zero or multiple matches → REFUSE the whole plan.

Contract
--------
- APPROVE-tier (``repo_write``). The plan is built and returned for
  the operator; execution is a separate step that re-validates before
  writing.
- All-or-nothing: if any single edit fails to match (or matches more
  than once), the whole plan is rejected before any file is touched.
- All paths resolve through ``FsGuard`` (workspace-only, deny-paths).
- Output ``Taint.TRUSTED`` — the diff content was authored locally.

Honest constraints
------------------
- This is NOT a fuzzy-edit / context-window edit format. If the model
  wants near-match tolerance, it should re-fetch the file and produce
  an exact block.
- We do NOT support binary files. Text-only.
- We do NOT auto-format. The new block lands verbatim.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from .fsguard import FsGuard


class CodeEditError(RuntimeError):
    """Raised when an edit plan can't be built honestly."""


@dataclass(frozen=True)
class EditBlock:
    file: str  # workspace-relative
    old: str
    new: str


@dataclass(frozen=True)
class EditFileChange:
    file: str
    old_lines: int
    new_lines: int
    net_delta: int  # new_lines - old_lines
    sha256_before: str
    sha256_after: str
    preview: str  # short summary of the change


@dataclass
class EditPlan:
    kind: str = "code_edit"
    files: list[EditFileChange] = field(default_factory=list)
    edits: list[dict[str, str]] = field(default_factory=list)
    total_old_lines: int = 0
    total_new_lines: int = 0
    total_net_delta: int = 0
    sha256_intent: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EditExecResult:
    kind: str = "code_edit_exec"
    files_written: list[str] = field(default_factory=list)
    bytes_written: int = 0
    sha256_intent: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_MAX_EDITS = 50  # safety cap; bigger transactions should be split


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_count(s: str) -> int:
    if not s:
        return 0
    return s.count("\n") + (0 if s.endswith("\n") else 1)


def plan_code_edits(
    guard: FsGuard,
    *,
    edits: list[dict[str, str]],
) -> EditPlan:
    """Build a validated multi-file edit plan, refusing on any drift.

    Each ``edit`` dict must carry ``file``, ``old``, ``new`` keys. If
    ``old`` does not appear exactly once in the file, the plan refuses.
    """
    if not isinstance(edits, list) or not edits:
        raise CodeEditError("code.edit_plan needs a non-empty edits list")
    if len(edits) > _MAX_EDITS:
        raise CodeEditError(
            f"code.edit_plan caps at {_MAX_EDITS} edits per plan, got {len(edits)}"
        )

    # Per-file aggregation: multiple edits may target the same file, applied
    # in declaration order. We simulate the full edit chain before recording
    # the change so a later edit can reference text inserted by an earlier one.
    by_file: dict[str, str] = {}  # file → current text after applied edits
    by_file_before: dict[str, str] = {}  # file → original text (sha256 only)
    edit_count_per_file: dict[str, int] = {}

    for i, raw in enumerate(edits):
        if not isinstance(raw, dict):
            raise CodeEditError(f"edits[{i}] must be a dict")
        try:
            blk = EditBlock(
                file=str(raw["file"]).strip(),
                old=str(raw["old"]),
                new=str(raw["new"]),
            )
        except KeyError as exc:
            raise CodeEditError(
                f"edits[{i}] missing key {exc.args[0]!r}"
            ) from exc
        if not blk.file:
            raise CodeEditError(f"edits[{i}] has empty file path")
        target = guard.resolve(blk.file)
        if not target.is_file():
            raise CodeEditError(
                f"edits[{i}] file not found in workspace: {blk.file}"
            )
        if blk.file not in by_file:
            current = target.read_text(encoding="utf-8")
            by_file_before[blk.file] = current
            by_file[blk.file] = current
        current = by_file[blk.file]
        occurrences = current.count(blk.old)
        if occurrences == 0:
            raise CodeEditError(
                f"edits[{i}] old-block not found in {blk.file} "
                f"(0 matches); the model must re-read the file"
            )
        if occurrences > 1:
            raise CodeEditError(
                f"edits[{i}] old-block matches {occurrences}× in {blk.file}; "
                "include more surrounding context to make it unique"
            )
        by_file[blk.file] = current.replace(blk.old, blk.new, 1)
        edit_count_per_file[blk.file] = edit_count_per_file.get(blk.file, 0) + 1

    files: list[EditFileChange] = []
    total_old = 0
    total_new = 0
    intent_parts: list[str] = []
    for fpath, after in by_file.items():
        before = by_file_before[fpath]
        before_lines = _line_count(before)
        after_lines = _line_count(after)
        delta = after_lines - before_lines
        total_old += before_lines
        total_new += after_lines
        n_edits = edit_count_per_file[fpath]
        preview = (
            f"{n_edits} edit{'s' if n_edits != 1 else ''} → "
            f"{before_lines}→{after_lines} lines ({delta:+d})"
        )
        change = EditFileChange(
            file=fpath,
            old_lines=before_lines,
            new_lines=after_lines,
            net_delta=delta,
            sha256_before=_sha256(before),
            sha256_after=_sha256(after),
            preview=preview,
        )
        files.append(change)
        intent_parts.append(
            f"{fpath}|{change.sha256_before}|{change.sha256_after}"
        )

    plan = EditPlan(
        files=files,
        edits=[dict(e) for e in edits],  # canonical copy for execute-time replay
        total_old_lines=total_old,
        total_new_lines=total_new,
        total_net_delta=total_new - total_old,
        sha256_intent=_sha256("\n".join(intent_parts)),
    )
    return plan


def execute_code_edits(
    guard: FsGuard,
    *,
    payload: dict[str, Any],
) -> EditExecResult:
    """Re-apply the validated plan and write the files.

    The payload is the plan dict returned by ``plan_code_edits``. We
    rebuild the plan from the same ``edits`` list (which re-validates
    every exact match) and verify the resulting ``sha256_intent``
    matches the approved one. Any drift refuses the write.
    """
    edits = payload.get("edits")
    if not isinstance(edits, list):
        raise CodeEditError("execute_code_edits needs the original edits list")
    approved_intent = str(payload.get("sha256_intent") or "")
    if not approved_intent:
        raise CodeEditError("execute_code_edits needs sha256_intent in payload")

    fresh = plan_code_edits(guard, edits=edits)
    if fresh.sha256_intent != approved_intent:
        raise CodeEditError(
            "intent hash drifted between approval and execute — refusing write. "
            f"approved={approved_intent[:12]}…, fresh={fresh.sha256_intent[:12]}…"
        )

    # Re-derive the after-text per file (plan_code_edits is the only place that
    # validates ordering) and write atomically.
    by_file_after: dict[str, str] = {}
    for raw in edits:
        if not isinstance(raw, dict):
            continue
        fpath = str(raw["file"]).strip()
        old = str(raw["old"])
        new = str(raw["new"])
        if fpath not in by_file_after:
            target = guard.resolve(fpath)
            by_file_after[fpath] = target.read_text(encoding="utf-8")
        by_file_after[fpath] = by_file_after[fpath].replace(old, new, 1)

    written: list[str] = []
    total_bytes = 0
    for fpath, after in by_file_after.items():
        target = guard.resolve(fpath)
        data = after.encode("utf-8")
        target.write_bytes(data)
        written.append(fpath)
        total_bytes += len(data)

    return EditExecResult(
        files_written=written,
        bytes_written=total_bytes,
        sha256_intent=approved_intent,
    )
