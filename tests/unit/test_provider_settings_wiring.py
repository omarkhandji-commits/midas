"""ProviderManager.add() wires the cheap role and writes .env on first key.

This closes the silent dead-end where a key entered in the dashboard landed in
the keychain but the agent kept using the default model — see WS-B in the plan.
"""

from __future__ import annotations

from pathlib import Path

from midas.core.config.models import ProviderEntry, ProvidersConfig, RoleConfig
from midas.flagship.provider_settings import MemorySecretVault, ProviderManager


def _empty_config() -> ProvidersConfig:
    return ProvidersConfig(
        providers={
            "openai": ProviderEntry(api_key_env="OPENAI_API_KEY"),
            "anthropic": ProviderEntry(api_key_env="ANTHROPIC_API_KEY"),
            "ollama": ProviderEntry(base_url_env="OLLAMA_BASE_URL"),
        },
        roles={},
    )


def test_add_with_key_wires_cheap_role_and_writes_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env: dict[str, str] = {}
    mgr = ProviderManager(_empty_config(), MemorySecretVault(), env=env, env_path=env_path)

    mgr.add("openai", api_key="sk-test")

    assert mgr.config.roles["cheap"].primary == "openai/gpt-4o-mini"
    assert env.get("MIDAS_MODEL_CHEAP") == "openai/gpt-4o-mini"
    written = env_path.read_text(encoding="utf-8")
    assert "MIDAS_MODEL_CHEAP=openai/gpt-4o-mini" in written
    assert "sk-test" not in written  # secret stays in the keychain


def test_add_does_not_overwrite_explicit_choice(tmp_path: Path) -> None:
    env = {"MIDAS_MODEL_CHEAP": "openrouter/auto"}
    mgr = ProviderManager(
        _empty_config(),
        MemorySecretVault(),
        env=env,
        env_path=tmp_path / ".env",
    )

    mgr.add("anthropic", api_key="sk-ant-test")

    assert env["MIDAS_MODEL_CHEAP"] == "openrouter/auto"
    assert "cheap" not in mgr.config.roles  # untouched


def test_add_does_not_overwrite_configured_role(tmp_path: Path) -> None:
    cfg = _empty_config()
    cfg.roles["cheap"] = RoleConfig(primary="ollama/llama3.1", fallbacks=[])
    env = {"OLLAMA_BASE_URL": "http://127.0.0.1:11434"}  # ollama is locally usable
    mgr = ProviderManager(cfg, MemorySecretVault(), env=env, env_path=tmp_path / ".env")

    mgr.add("openai", api_key="sk-test")

    # Existing satisfied role stays; only new key lands in vault.
    assert mgr.config.roles["cheap"].primary == "ollama/llama3.1"


def test_add_overwrites_unsatisfied_role(tmp_path: Path) -> None:
    cfg = _empty_config()
    # Previous user pointed cheap at openai but never provided the key:
    cfg.roles["cheap"] = RoleConfig(primary="openai/gpt-4o-mini", fallbacks=[])
    env: dict[str, str] = {}
    mgr = ProviderManager(cfg, MemorySecretVault(), env=env, env_path=tmp_path / ".env")

    # The new provider IS configured (we add a real key), so it should take over.
    mgr.add("anthropic", api_key="sk-ant-test")

    assert mgr.config.roles["cheap"].primary == "anthropic/claude-3-5-haiku-latest"


def test_add_without_env_path_skips_persistence(tmp_path: Path) -> None:
    """Backwards-compat: dashboard tests that pass ``env={}`` and no path still pass.

    The role mutation still happens (so the running router picks it up), but no
    file is touched — exactly the contract the existing dashboard tests rely on.
    """
    env: dict[str, str] = {}
    mgr = ProviderManager(_empty_config(), MemorySecretVault(), env=env)

    mgr.add("openai", api_key="sk-test")

    assert mgr.config.roles["cheap"].primary == "openai/gpt-4o-mini"
    assert env.get("MIDAS_MODEL_CHEAP") == "openai/gpt-4o-mini"
    # No .env to write to is fine.
