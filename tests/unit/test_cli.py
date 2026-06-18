"""CLI smoke tests: version + the offline scan demo produce a Daily Revenue Move."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from midas.flagship.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "MIDAS" in result.stdout


def test_scan_demo_prints_daily_revenue_move() -> None:
    result = runner.invoke(app, ["scan", "tools for plumbers"])
    assert result.exit_code == 0
    assert "DAILY REVENUE MOVE" in result.stdout
    assert "Proof:" in result.stdout
    assert "requires your approval" in result.stdout  # approval-default
    assert "No revenue is promised" in result.stdout


def test_scan_accepts_run_mode() -> None:
    result = runner.invoke(app, ["scan", "tools for plumbers", "--mode", "war-room"])
    assert result.exit_code == 0
    assert "DAILY REVENUE MOVE" in result.stdout


def test_repo_map_command(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "core.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    result = runner.invoke(app, ["repo-map", ".", "--base-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert "Repo map:" in result.stdout
    assert "pkg/core.py" in result.stdout


def test_blog_lint_command(tmp_path: Path) -> None:
    post = tmp_path / "post.md"
    post.write_text("# One title\n\nShort body.\n", encoding="utf-8")

    result = runner.invoke(app, ["blog-lint", str(post)])

    assert result.exit_code == 0
    assert "SEO score:" in result.stdout


def test_course_command() -> None:
    result = runner.invoke(
        app,
        ["course", "AI automation for freelancers", "--modules", "3"],
    )

    assert result.exit_code == 0
    assert "# AI automation for freelancers" in result.stdout
    assert "Module 1" in result.stdout
