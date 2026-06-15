"""Structured data read/write — JSON and CSV.

All paths flow through :class:`FsGuard`. Writes are AUTO when the path lives inside
the workspace AND has no prior content sha conflict; otherwise the agent should
use ``fs.write`` (gated) instead. To keep the security boundary clean, this module
exposes **planners only** for writes — actual disk mutation reuses ``execute_fs_write``.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

from .fs import FsWritePlan, plan_fs_write
from .fsguard import FsGuard


@dataclass(frozen=True)
class JsonReadResult:
    path: str
    data: Any
    size_bytes: int


@dataclass(frozen=True)
class CsvReadResult:
    path: str
    rows: list[list[str]]
    n_rows: int
    n_cols: int


def json_read(guard: FsGuard, path: str) -> JsonReadResult:
    target = guard.resolve(path, must_exist=True)
    raw = target.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {target}: {exc}") from exc
    return JsonReadResult(path=str(target), data=data, size_bytes=len(raw.encode("utf-8")))


def plan_json_write(guard: FsGuard, path: str, data: Any, *, indent: int = 2) -> FsWritePlan:
    """Approval payload for a JSON write — reuses the fs.write gating chain."""
    content = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=True)
    return plan_fs_write(guard, path, content)


def csv_read(guard: FsGuard, path: str, *, max_rows: int = 5000) -> CsvReadResult:
    target = guard.resolve(path, must_exist=True)
    with target.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))[:max_rows]
    return CsvReadResult(
        path=str(target),
        rows=[list(r) for r in rows],
        n_rows=len(rows),
        n_cols=max((len(r) for r in rows), default=0),
    )


def plan_csv_write(guard: FsGuard, path: str, rows: list[list[Any]]) -> FsWritePlan:
    """Approval payload for a CSV write — reuses the fs.write gating chain."""
    if not isinstance(rows, list):
        raise ValueError("rows must be a list of lists")
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return plan_fs_write(guard, path, buf.getvalue())
