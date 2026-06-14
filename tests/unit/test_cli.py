"""CLI smoke tests: version + the offline scan demo produce a Daily Revenue Move."""

from __future__ import annotations

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
