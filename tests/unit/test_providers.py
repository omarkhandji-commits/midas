"""Provider diagnostics and CLI wiring for local + multi-provider MIDAS."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from midas.core.config.models import ProviderEntry, ProvidersConfig
from midas.core.providers import diagnose_providers
from midas.flagship.cli import app

runner = CliRunner()


def test_ollama_is_local_ready_without_key() -> None:
    cfg = ProvidersConfig(providers={"ollama": ProviderEntry(base_url_env="OLLAMA_BASE_URL")})
    statuses = {s.name: s for s in diagnose_providers(cfg, env={})}
    assert statuses["ollama"].configured is True
    assert statuses["ollama"].local is True


def test_key_provider_reports_missing_env() -> None:
    cfg = ProvidersConfig(providers={"openrouter": ProviderEntry(api_key_env="OPENROUTER_API_KEY")})
    statuses = {s.name: s for s in diagnose_providers(cfg, env={})}
    assert statuses["openrouter"].configured is False
    assert statuses["openrouter"].missing == ("OPENROUTER_API_KEY",)


def test_providers_add_writes_safe_metadata_only(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "ollama",
            "--role",
            "cheap",
            "--model",
            "ollama/llama3.1",
            "--base-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.stdout
    data = yaml.safe_load((tmp_path / "config" / "providers.yml").read_text(encoding="utf-8"))
    assert data["providers"]["ollama"]["base_url_env"] == "OLLAMA_BASE_URL"
    assert data["roles"]["cheap"]["primary"] == "ollama/llama3.1"
    assert "api_key" not in str(data).lower()


def test_council_dry_run_needs_no_api_key() -> None:
    result = runner.invoke(app, ["council", "Should we launch this offer?"])
    assert result.exit_code == 0, result.stdout
    assert "Agreement:" in result.stdout
    assert "Human approval needed:" in result.stdout
