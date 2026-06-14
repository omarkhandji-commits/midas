"""Scheduler recipes and security-first skill registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from midas.flagship.cli import app
from midas.flagship.schedule import ScheduleStore, daily_scan_recipe
from midas.flagship.skills import SkillRegistry

runner = CliRunner()


def test_daily_scan_recipe_is_user_installed_not_auto_run() -> None:
    recipe = daily_scan_recipe(
        name="local-seo",
        niche="agence SEO locale",
        at="08:30",
        base_dir="C:/repo",
        mode="war-room",
    )
    assert "midas scan" in recipe.command
    assert "schtasks /Create" in recipe.windows_task
    assert "30 8 * * *" in recipe.cron_line
    assert "workflow_dispatch" in recipe.github_actions


def test_schedule_store_round_trips(tmp_path: Path) -> None:
    store = ScheduleStore(tmp_path / "schedules.json")
    recipe = daily_scan_recipe(name="daily", niche="plumbers")
    store.add(recipe)
    assert store.list()[0].name == "daily"


def test_skill_registry_creates_safe_template(tmp_path: Path) -> None:
    registry = SkillRegistry(tmp_path)
    manifest = registry.create(name="Market Radar Pro", summary="Track market changes.")
    skill_path = tmp_path / "skills" / manifest.name / "SKILL.md"
    assert skill_path.exists()
    assert manifest.permissions == ["read"]
    assert registry.list()[0].sha256 == manifest.sha256


def test_skill_install_rejects_executable_payload(tmp_path: Path) -> None:
    source = tmp_path / "unsafe"
    source.mkdir()
    (source / "SKILL.md").write_text("# Unsafe\n", encoding="utf-8")
    (source / "run.ps1").write_text("Write-Host nope", encoding="utf-8")
    with pytest.raises(ValueError, match="denied executable"):
        SkillRegistry(tmp_path / "registry").install_local(source)


def test_remote_skill_download_is_approval_only() -> None:
    result = runner.invoke(
        app,
        ["skills", "plan-download", "https://example.com/skill.git", "--reason", "test"],
    )
    assert result.exit_code == 0, result.stdout
    assert "Approval queued" in result.stdout
