"""WS-OpenAICompat — ProviderManager.quick_connect wires any OpenAI-compatible endpoint.

Covers:
- URL + key + model are all required, http(s) only.
- After call: vault contains OPENAI_API_KEY + OPENAI_API_BASE; env has the same
  + MIDAS_MODEL_CHEAP; in-memory roles[cheap].primary == openai/<model>.
- env_path on disk receives the new MIDAS_MODEL_CHEAP and OPENAI_API_BASE so the
  agent picks the change on restart, not just in-process.
- Does not depend on a real network or a real keyring backend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.config.models import (
    ProviderEntry,
    ProvidersConfig,
    RoleConfig,
)
from midas.flagship.provider_settings import MemorySecretVault, ProviderManager


def _make_manager(
    tmp_path: Path,
) -> tuple[ProviderManager, MemorySecretVault, dict[str, str], Path]:
    env: dict[str, str] = {}
    env_path = tmp_path / ".env"
    env_path.write_text("OLLAMA_BASE_URL=http://127.0.0.1:11434\n", encoding="utf-8")
    config = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="ollama/llama3.1:8b", fallbacks=[])},
        providers={
            "openai_compatible": ProviderEntry(
                api_key_env="OPENAI_COMPATIBLE_API_KEY",
                base_url_env="OPENAI_COMPATIBLE_BASE_URL",
            ),
        },
    )
    vault = MemorySecretVault()
    mgr = ProviderManager(config, vault, env=env, env_path=env_path)
    return mgr, vault, env, env_path


def test_quick_connect_wires_vault_env_role_and_envfile(tmp_path: Path) -> None:
    mgr, vault, env, env_path = _make_manager(tmp_path)

    result = mgr.quick_connect(
        base_url="https://opencode.ai/zen/v1",
        api_key="oc-zen-test-token",
        model_name="big",
    )

    assert result == {
        "ok": True,
        "role": "cheap",
        "model": "openai/big",
        "base_url": "https://opencode.ai/zen/v1",
    }

    assert vault.get("OPENAI_API_KEY") == "oc-zen-test-token"
    assert vault.get("OPENAI_API_BASE") == "https://opencode.ai/zen/v1"
    assert env["OPENAI_API_KEY"] == "oc-zen-test-token"
    assert env["OPENAI_API_BASE"] == "https://opencode.ai/zen/v1"
    assert env["MIDAS_MODEL_CHEAP"] == "openai/big"

    role = mgr.config.roles["cheap"]
    assert role.primary == "openai/big"

    env_text = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_BASE=https://opencode.ai/zen/v1" in env_text
    assert "MIDAS_MODEL_CHEAP=openai/big" in env_text
    assert "OLLAMA_BASE_URL=http://127.0.0.1:11434" in env_text  # preserved


def test_quick_connect_requires_all_three_inputs(tmp_path: Path) -> None:
    mgr, *_ = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="required"):
        mgr.quick_connect(base_url="https://x.com", api_key="", model_name="big")
    with pytest.raises(ValueError, match="required"):
        mgr.quick_connect(base_url="", api_key="k", model_name="big")
    with pytest.raises(ValueError, match="required"):
        mgr.quick_connect(base_url="https://x.com", api_key="k", model_name="")


def test_quick_connect_refuses_non_http_url(tmp_path: Path) -> None:
    mgr, *_ = _make_manager(tmp_path)
    with pytest.raises(ValueError, match="http"):
        mgr.quick_connect(base_url="ftp://x.com", api_key="k", model_name="m")


def test_quick_connect_preserves_existing_fallbacks(tmp_path: Path) -> None:
    mgr, *_ = _make_manager(tmp_path)
    mgr.config.roles["cheap"] = RoleConfig(
        primary="ollama/llama3.1:8b",
        fallbacks=["openrouter/auto"],
    )

    mgr.quick_connect(base_url="https://api.x.com/v1", api_key="k", model_name="m")

    assert mgr.config.roles["cheap"].primary == "openai/m"
    assert mgr.config.roles["cheap"].fallbacks == ["openrouter/auto"]
