"""WS-LLMConnect — discover-models + use-model endpoints.

Covers:
- discover_models hits <url>/models with Bearer auth and returns sorted unique ids
- discover_models surfaces actionable errors (401, 404, non-JSON, unreachable)
- use_model mutates roles[role].primary in-place AND persists MIDAS_MODEL_CHEAP
- use_model preserves the role's fallbacks
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.flagship.provider_settings import MemorySecretVault, ProviderManager


def _make(tmp_path: Path) -> ProviderManager:
    env: dict[str, str] = {}
    env_path = tmp_path / ".env"
    env_path.write_text("OLLAMA_BASE_URL=http://127.0.0.1:11434\n", encoding="utf-8")
    config = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="ollama/llama3.1:8b", fallbacks=["openrouter/auto"])},
    )
    return ProviderManager(config, MemorySecretVault(), env=env, env_path=env_path)


def _ok(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_discover_models_returns_sorted_unique_ids(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    payload = {
        "data": [
            {"id": "gpt-5"},
            {"id": "gpt-4o-mini"},
            {"id": "gpt-5"},  # duplicate
            {"id": "claude-sonnet-4"},
        ],
    }
    with patch("httpx.get", return_value=_ok(payload)):
        models = mgr.discover_models(base_url="https://api.example.com/v1", api_key="k")
    assert models == ["claude-sonnet-4", "gpt-4o-mini", "gpt-5"]


def test_discover_models_handles_bare_list_payload(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with patch("httpx.get", return_value=_ok(["m1", "m2"])):
        assert mgr.discover_models(base_url="https://x.com", api_key="k") == ["m1", "m2"]


def test_discover_models_sends_bearer_when_key_present(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _ok({"data": []})

    with patch("httpx.get", side_effect=fake_get):
        mgr.discover_models(base_url="https://api.example.com/v1", api_key="secret")
    assert captured["url"] == "https://api.example.com/v1/models"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("Authorization") == "Bearer secret"


def test_discover_models_401_surfaces_actionable_error(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with patch("httpx.get", return_value=httpx.Response(401, json={"error": "bad"})):
        with pytest.raises(ValueError, match="key rejected"):
            mgr.discover_models(base_url="https://x.com", api_key="bad")


def test_discover_models_404_suggests_url_fix(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with patch("httpx.get", return_value=httpx.Response(404, json={})):
        with pytest.raises(ValueError, match="/models route"):
            mgr.discover_models(base_url="https://x.com", api_key="k")


def test_discover_models_non_json_payload(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with patch("httpx.get", return_value=httpx.Response(200, content=b"<html>oops</html>")):
        with pytest.raises(ValueError, match="not JSON"):
            mgr.discover_models(base_url="https://x.com", api_key="k")


def test_discover_models_unreachable(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with patch("httpx.get", side_effect=httpx.ConnectError("nope")):
        with pytest.raises(ValueError, match="unreachable"):
            mgr.discover_models(base_url="https://x.com", api_key="k")


def test_discover_models_requires_http_scheme(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with pytest.raises(ValueError, match="http"):
        mgr.discover_models(base_url="ftp://x.com", api_key="k")


def test_use_model_mutates_role_and_persists_env(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    result = mgr.use_model("openai/gpt-5")
    assert result == {"ok": True, "role": "cheap", "model": "openai/gpt-5"}
    assert mgr.config.roles["cheap"].primary == "openai/gpt-5"
    assert mgr.config.roles["cheap"].fallbacks == ["openrouter/auto"]
    assert mgr.env["MIDAS_MODEL_CHEAP"] == "openai/gpt-5"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MIDAS_MODEL_CHEAP=openai/gpt-5" in env_text
    assert "OLLAMA_BASE_URL=http://127.0.0.1:11434" in env_text


def test_use_model_refuses_empty_id(tmp_path: Path) -> None:
    mgr = _make(tmp_path)
    with pytest.raises(ValueError, match="required"):
        mgr.use_model("")
