"""code.repo_map — AST-based map of Python files + import-graph ranking.

Why
---
The Aider/Polyglot family of coding agents share one consistent trick:
they don't dump the whole repo into the LLM, they precompute a *map* of
which files matter most and only feed the planner the relevant slices.
This module is the foundation of MIDAS's native coder — Phase 6, step 1.

What it does
------------
1. Walks the workspace for ``.py`` files (respecting common ignore dirs).
2. Parses each with the stdlib ``ast`` module — no third-party deps, no
   tree-sitter native build.
3. Extracts top-level functions, top-level classes, and import edges.
4. Builds a coarse-grained import graph (resolved by module name) and
   ranks files by in-degree — files imported by many others bubble up.

Honest constraints
------------------
- This is NOT real PageRank — we don't iterate to fixpoint. In-degree
  is a 90%-correct heuristic that runs in linear time and has no
  third-party dependency. A future slice can swap in a tighter score.
- We only parse Python in this slice. JS/TS/Go ranking is a follow-up;
  the symbol-graph data shape is language-agnostic so the extension is
  additive.
- We do NOT execute any code in the repo. Parse-only. Files that fail
  to parse are recorded with the error reason, not raised.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .fsguard import FsGuard

_IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".midas", ".midas-state", "build", "dist", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox",
}
_MAX_FILES = 5_000  # safety cap; bigger repos need pagination, future slice


@dataclass(frozen=True)
class FileEntry:
    path: str  # workspace-relative, posix-style
    module: str  # dotted module name when resolvable, else ""
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)  # dotted names
    score: float = 0.0  # in-degree rank, higher = more depended on
    parse_error: str = ""  # non-empty means we couldn't parse it

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepoMap:
    root: str
    files: list[FileEntry] = field(default_factory=list)
    file_count: int = 0
    parse_errors: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "file_count": self.file_count,
            "parse_errors": self.parse_errors,
            "files": [f.to_dict() for f in self.files],
        }

    def top(self, n: int = 20) -> list[FileEntry]:
        """The top-N most depended-on files."""
        return sorted(self.files, key=lambda f: f.score, reverse=True)[:n]


def _module_for(path: Path, root: Path) -> str:
    """Best-effort dotted name from a path under root, '' if not derivable."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return ""
    parts = list(rel.with_suffix("").parts)
    # Strip leading 'src' if present — common layout.
    if parts and parts[0] == "src":
        parts = parts[1:]
    # __init__.py represents the package itself.
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _walk_py(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if parts & _IGNORE_DIRS:
            continue
        if not p.is_file():
            continue
        out.append(p)
        if len(out) >= _MAX_FILES:
            break
    return out


def _extract(tree: ast.Module) -> tuple[list[str], list[str], list[str]]:
    """(functions, classes, imports) at module top-level."""
    funcs: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            funcs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return funcs, classes, imports


def build_repo_map(guard: FsGuard, *, subdir: str = ".") -> RepoMap:
    """Walk ``subdir`` (workspace-relative), parse Python files, rank by in-degree."""
    root = guard.resolve(subdir)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"repo_map needs an existing directory, got {subdir!r}")

    files = _walk_py(root)
    entries: list[FileEntry] = []
    by_module: dict[str, FileEntry] = {}
    parse_errors = 0

    for p in files:
        module = _module_for(p, root)
        rel = p.relative_to(root).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError) as exc:
            parse_errors += 1
            entry = FileEntry(
                path=rel, module=module,
                parse_error=f"{type(exc).__name__}: {exc}"[:200],
            )
            entries.append(entry)
            if module:
                by_module[module] = entry
            continue
        funcs, classes, imports = _extract(tree)
        entry = FileEntry(
            path=rel, module=module,
            functions=funcs, classes=classes, imports=imports,
        )
        entries.append(entry)
        if module:
            by_module[module] = entry

    # Score: in-degree, weighted by the prefix-longest-match.
    # If file B imports "midas.core.x" and module "midas.core.x" exists,
    # bump that target by 1. Falls back to longest-prefix module if the
    # exact import name doesn't resolve (handles "from pkg import sym").
    counts: Counter[str] = Counter()
    module_names = sorted(by_module.keys(), key=len, reverse=True)
    for e in entries:
        for imp in e.imports:
            if imp in by_module:
                counts[imp] += 1
                continue
            for m in module_names:
                if imp.startswith(m + "."):
                    counts[m] += 1
                    break

    # Re-emit entries with their score baked in (FileEntry is frozen).
    scored: list[FileEntry] = []
    for e in entries:
        scored.append(
            FileEntry(
                path=e.path, module=e.module,
                functions=e.functions, classes=e.classes,
                imports=e.imports, parse_error=e.parse_error,
                score=float(counts.get(e.module, 0)) if e.module else 0.0,
            )
        )

    return RepoMap(
        root=str(root),
        files=scored,
        file_count=len(scored),
        parse_errors=parse_errors,
    )
