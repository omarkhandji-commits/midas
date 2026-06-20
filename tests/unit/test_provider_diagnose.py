"""WS-Doctor — ProviderManager.diagnose + OpenAI-compat alias bridge.

Verifies:
- diagnose() returns one row per known handle with vault/env presence flags
- apply_to_environment now mirrors OPENAI_COMPATIBLE_* → OPENAI_API_* when the
  canonical names are missing — closing the "connected but chat fails" gap
- Mirror is no-op when canonical names already set
"""

from __future__ import annotations

from pathlib import Path

from midas.core.config.models import ProviderEntry, ProvidersConfig
from midas.flagship.provider_settings import MemorySecretVault, ProviderManager


def _make(
    tmp_path: Path,
    env: dict[str, str] | None = None,
) -> tuple[ProviderManager, MemorySecretVault, dict[str, str]]:
    env_dict: dict[str, str] = env or {}
    config = ProvidersConfig(
        providers={
            "openai_compatible": ProviderEntry(
                api_key_env="OPENAI_COMPATIBLE_API_KEY",
                base_url_env="OPENAI_COMPATIBLE_BASE_URL",
            ),
        },
    )
    vault = MemorySecretVault()
    mgr = ProviderManager(config, vault, env=env_dict, env_path=tmp_path / ".env")
    return mgr, vault, env_dict


def test_apply_to_environment_aliases_openai_compatible_key(tmp_path: Path) -> None:
    mgr, vault, env = _make(tmp_path)
    vault.set("OPENAI_COMPATIBLE_API_KEY", "oc-real-key")
    vault.set("OPENAI_COMPATIBLE_BASE_URL", "https://opencode.ai/zen/v1")

    mgr.apply_to_environment()

    assert env["OPENAI_API_KEY"] == "oc-real-key"
    assert env["OPENAI_API_BASE"] == "https://opencode.ai/zen/v1"


def test_apply_to_environment_does_not_overwrite_canonical(tmp_path: Path) -> None:
    mgr, vault, env = _make(tmp_path)
    vault.set("OPENAI_API_KEY", "sk-real-openai")
    vault.set("OPENAI_COMPATIBLE_API_KEY", "should-not-win")

    mgr.apply_to_environment()

    assert env["OPENAI_API_KEY"] == "sk-real-openai"


def test_diagnose_reports_vault_and_env_state(tmp_path: Path) -> None:
    mgr, vault, env = _make(tmp_path)
    vault.set("OPENAI_COMPATIBLE_API_KEY", "k")
    env["OPENAI_API_BASE"] = "https://x.com/v1"

    rows = mgr.diagnose()

    by_handle = {r["handle"]: r for r in rows}
    assert by_handle["OPENAI_COMPATIBLE_API_KEY"]["in_vault"] is True
    assert by_handle["OPENAI_COMPATIBLE_API_KEY"]["in_env"] is False
    # OPENAI_API_BASE shows as in_env (set above) and not in_vault
    canonical = by_handle.get("OPENAI_API_BASE")
    assert canonical is not None
    assert canonical["in_env"] is True
    assert canonical["in_vault"] is False
    # Canonical OPENAI_API_KEY should always be reported even with no vault entry
    api_key = by_handle.get("OPENAI_API_KEY")
    assert api_key is not None
    assert api_key["in_vault"] is False
