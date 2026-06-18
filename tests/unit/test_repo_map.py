"""code.repo_map — AST walk + in-degree ranking."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.repo_map import build_repo_map


def _guard(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return FsGuard(workspace=ws.resolve())


def test_finds_python_files_and_extracts_symbols(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text(
        "def foo(): pass\nclass Bar: pass\n", encoding="utf-8"
    )
    rmap = build_repo_map(guard)
    assert rmap.file_count == 1
    f = rmap.files[0]
    assert f.path == "a.py"
    assert "foo" in f.functions
    assert "Bar" in f.classes


def test_in_degree_ranks_imported_module_higher(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "core.py").write_text("X = 1\n", encoding="utf-8")
    (guard.workspace / "a.py").write_text("import core\n", encoding="utf-8")
    (guard.workspace / "b.py").write_text("from core import X\n", encoding="utf-8")
    rmap = build_repo_map(guard)
    by_path = {f.path: f for f in rmap.files}
    assert by_path["core.py"].score == 2.0
    assert by_path["a.py"].score == 0.0


def test_top_returns_highest_score_first(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "shared.py").write_text("Y = 1\n", encoding="utf-8")
    (guard.workspace / "leaf.py").write_text("Z = 1\n", encoding="utf-8")
    (guard.workspace / "a.py").write_text("import shared\n", encoding="utf-8")
    (guard.workspace / "b.py").write_text("import shared\n", encoding="utf-8")
    rmap = build_repo_map(guard)
    top = rmap.top(n=1)
    assert top[0].path == "shared.py"


def test_records_parse_error_without_raising(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "broken.py").write_text("def (:\n", encoding="utf-8")
    rmap = build_repo_map(guard)
    assert rmap.parse_errors == 1
    assert rmap.files[0].parse_error.startswith("SyntaxError")


def test_skips_ignored_dirs(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "__pycache__").mkdir()
    (guard.workspace / "__pycache__" / "junk.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    (guard.workspace / ".venv").mkdir()
    (guard.workspace / ".venv" / "junk.py").write_text("x = 1\n", encoding="utf-8")
    (guard.workspace / "real.py").write_text("y = 1\n", encoding="utf-8")
    rmap = build_repo_map(guard)
    paths = {f.path for f in rmap.files}
    assert paths == {"real.py"}


def test_module_name_strips_src_prefix(tmp_path):
    guard = _guard(tmp_path)
    pkg = guard.workspace / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("def hi(): pass\n", encoding="utf-8")
    rmap = build_repo_map(guard)
    modules = {f.module for f in rmap.files}
    assert "pkg.mod" in modules


def test_refuses_missing_subdir(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        build_repo_map(_guard(tmp_path), subdir="does-not-exist")


def test_imports_resolved_to_longest_prefix(tmp_path):
    guard = _guard(tmp_path)
    deep = guard.workspace / "src" / "midas" / "core"
    deep.mkdir(parents=True)
    (deep / "__init__.py").write_text("", encoding="utf-8")
    (deep / "x.py").write_text("V = 1\n", encoding="utf-8")
    # importer uses "from midas.core.x import V" — prefix match goes to midas.core.x
    (guard.workspace / "importer.py").write_text(
        "from midas.core.x import V\n", encoding="utf-8"
    )
    rmap = build_repo_map(guard)
    by_mod = {f.module: f for f in rmap.files if f.module}
    assert by_mod["midas.core.x"].score == 1.0
