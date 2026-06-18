"""code.edit_plan — exact-match validation, multi-file aggregation."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.code_edit import (
    CodeEditError,
    plan_code_edits,
)
from midas.flagship.agent.tools.fsguard import FsGuard


def _guard(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return FsGuard(workspace=ws.resolve())


def test_single_edit_replaces_unique_block(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text(
        "def foo():\n    return 1\n", encoding="utf-8"
    )
    plan = plan_code_edits(
        guard,
        edits=[{"file": "a.py", "old": "return 1", "new": "return 2"}],
    )
    assert len(plan.files) == 1
    assert plan.files[0].file == "a.py"
    assert plan.files[0].net_delta == 0
    assert plan.sha256_intent  # non-empty


def test_zero_match_refused(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(CodeEditError, match="not found"):
        plan_code_edits(
            guard,
            edits=[{"file": "a.py", "old": "nope", "new": "yes"}],
        )


def test_multi_match_refused(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text(
        "x = 1\ny = 1\nz = 1\n", encoding="utf-8"
    )
    with pytest.raises(CodeEditError, match="matches 3"):
        plan_code_edits(
            guard,
            edits=[{"file": "a.py", "old": "= 1", "new": "= 2"}],
        )


def test_multiple_edits_same_file_apply_in_order(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text(
        "alpha\nbeta\ngamma\n", encoding="utf-8"
    )
    plan = plan_code_edits(
        guard,
        edits=[
            {"file": "a.py", "old": "alpha", "new": "A1"},
            {"file": "a.py", "old": "beta", "new": "B2"},
        ],
    )
    assert plan.files[0].net_delta == 0
    assert "2 edits" in plan.files[0].preview


def test_edit_can_reference_text_inserted_by_earlier_edit(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text("OLD\n", encoding="utf-8")
    plan = plan_code_edits(
        guard,
        edits=[
            {"file": "a.py", "old": "OLD", "new": "NEW\nLINE2"},
            {"file": "a.py", "old": "LINE2", "new": "LINE2_FIXED"},
        ],
    )
    assert plan.files[0].new_lines == 2


def test_refuses_missing_file(tmp_path):
    guard = _guard(tmp_path)
    with pytest.raises(CodeEditError, match="not found in workspace"):
        plan_code_edits(
            guard,
            edits=[{"file": "ghost.py", "old": "x", "new": "y"}],
        )


def test_refuses_empty_edits(tmp_path):
    with pytest.raises(CodeEditError, match="non-empty edits list"):
        plan_code_edits(_guard(tmp_path), edits=[])


def test_caps_at_50_edits(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text("x", encoding="utf-8")
    too_many = [{"file": "a.py", "old": "x", "new": "y"}] * 51
    with pytest.raises(CodeEditError, match="caps at 50"):
        plan_code_edits(guard, edits=too_many)


def test_refuses_missing_keys(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text("x", encoding="utf-8")
    with pytest.raises(CodeEditError, match="missing key 'new'"):
        plan_code_edits(guard, edits=[{"file": "a.py", "old": "x"}])


def test_multi_file_aggregation(tmp_path):
    guard = _guard(tmp_path)
    (guard.workspace / "a.py").write_text("A\n", encoding="utf-8")
    (guard.workspace / "b.py").write_text("B\n", encoding="utf-8")
    plan = plan_code_edits(
        guard,
        edits=[
            {"file": "a.py", "old": "A", "new": "A1\nA2"},
            {"file": "b.py", "old": "B", "new": "B1"},
        ],
    )
    paths = {f.file for f in plan.files}
    assert paths == {"a.py", "b.py"}
    assert plan.total_net_delta == 1  # a.py +1 line, b.py +0
