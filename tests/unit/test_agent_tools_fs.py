"""fs.read / fs.list / fs.write tool behavior + guard integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.fs import (
    execute_fs_write,
    fs_list,
    fs_read,
    plan_fs_write,
)
from midas.flagship.agent.tools.fsguard import FsGuard, FsGuardError


def _g(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def test_fs_read_returns_content_and_sha256(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    g = _g(tmp_path)
    res = fs_read(g, "a.txt")
    assert res.text == "hello"
    assert res.size_bytes == 5
    assert res.sha256 and len(res.sha256) == 64


def test_fs_read_truncates_text_at_max_chars(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * 5000, encoding="utf-8")
    res = fs_read(_g(tmp_path), "big.txt", max_chars=100)
    assert len(res.text) == 100
    assert res.size_bytes == 5000  # original size preserved


def test_fs_list_orders_entries(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    res = fs_list(_g(tmp_path), ".")
    assert res.entries == ["a.txt", "b.txt"]


def test_plan_fs_write_does_not_touch_disk(tmp_path: Path) -> None:
    plan = plan_fs_write(_g(tmp_path), "out.txt", "data")
    assert plan.bytes_len == 4
    assert plan.sha256_prev is None
    assert plan.preview == "data"
    assert not (tmp_path / "out.txt").exists()  # NO write


def test_plan_fs_write_records_prev_sha256(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("old", encoding="utf-8")
    plan = plan_fs_write(_g(tmp_path), "out.txt", "new")
    assert plan.sha256_prev is not None
    assert plan.sha256_prev != plan.sha256_new


def test_execute_fs_write_writes_bytes(tmp_path: Path) -> None:
    plan = execute_fs_write(_g(tmp_path), "out.txt", "data")
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "data"
    assert plan.bytes_len == 4


def test_fs_read_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(FsGuardError):
        fs_read(_g(tmp_path), "../outside.txt")
