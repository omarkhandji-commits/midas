"""Config loader: the shipped policy.yml / providers.example.yml parse into typed models."""

from __future__ import annotations

from pathlib import Path

from midas.core.config import Autonomy, load_app_config, load_policy, load_providers

BASE = Path(__file__).resolve().parents[2]  # midas/


def test_policy_parses_from_shipped_file() -> None:
    policy = load_policy(BASE / "config" / "policy.yml")
    assert policy.autonomy == Autonomy.SEMI_AUTO  # approval-default (locked)
    assert policy.spend_caps.per_task == 0.25
    assert policy.spend_caps.daily == 2.0
    assert policy.spend_caps.monthly == 30.0
    # the "never" list is the hard-forbidden set the Sentinel enforces
    assert "spam" in policy.actions.never
    assert "leak_secret" in policy.actions.never
    # outbound actions require approval
    assert "send_email" in policy.actions.requires_approval
    assert "web_search" in policy.actions.allowed_without_approval
    # egress is deny-by-default (empty allowlist shipped)
    assert policy.egress_allowlist == []


def test_providers_parse_from_example() -> None:
    providers = load_providers(BASE / "config" / "providers.example.yml")
    assert "cheap" in providers.roles
    assert "smart" in providers.roles
    assert providers.roles["cheap"].primary  # non-empty
    assert providers.routing.default_role == "cheap"


def test_app_config_caps_and_autonomy() -> None:
    cfg = load_app_config(BASE)
    per_task, daily, monthly = cfg.caps()
    assert (per_task, daily, monthly) == (0.25, 2.0, 30.0)
    assert cfg.autonomy == Autonomy.SEMI_AUTO
    assert cfg.kill_switch is False


def test_env_file_exports_provider_keys_to_process(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "policy.yml").write_text(
        (BASE / "config" / "policy.yml").read_text(),
        encoding="utf-8",
    )
    (config_dir / "providers.example.yml").write_text(
        (BASE / "config" / "providers.example.yml").read_text(),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=from_file\n", encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    load_app_config(tmp_path)

    assert __import__("os").environ["OPENROUTER_API_KEY"] == "from_file"


def test_env_model_overrides_provider_roles(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "policy.yml").write_text(
        (BASE / "config" / "policy.yml").read_text(),
        encoding="utf-8",
    )
    (config_dir / "providers.example.yml").write_text(
        (BASE / "config" / "providers.example.yml").read_text(),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "MIDAS_MODEL_CHEAP=ollama/qwen2.5\nMIDAS_MODEL_SMART=openrouter/auto\n",
        encoding="utf-8",
    )

    cfg = load_app_config(tmp_path)

    assert cfg.providers.roles["cheap"].primary == "ollama/qwen2.5"
    assert cfg.providers.roles["smart"].primary == "openrouter/auto"
