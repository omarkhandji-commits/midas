"""Onboarding — provider detection, env upsert, config seeding."""

from __future__ import annotations

from pathlib import Path

from midas.flagship.onboard import (
    configure,
    ensure_providers_yml,
    pick_ollama_model,
    provider_from_key,
    upsert_env,
)


def test_provider_from_key_prefixes() -> None:
    assert provider_from_key("sk-ant-abc123").provider == "anthropic"
    assert provider_from_key("sk-or-xyz").provider == "openrouter"
    assert provider_from_key("gsk_abc").provider == "groq"
    assert provider_from_key("sk-proj-abc").provider == "openai"
    assert provider_from_key("sk-abc123def").provider == "openai"
    assert provider_from_key("AIzaSyABC").provider == "google"
    assert provider_from_key("totally-unknown-key") is None


def test_provider_from_key_maps_env_and_model() -> None:
    p = provider_from_key("sk-ant-xxx")
    assert p.env_var == "ANTHROPIC_API_KEY"
    assert p.model.startswith("anthropic/")


def test_pick_ollama_model_prefers_small_general() -> None:
    assert pick_ollama_model(["codellama:70b", "llama3.1:8b"]) == "llama3.1:8b"
    assert pick_ollama_model(["mistral:7b"]) == "mistral:7b"
    assert pick_ollama_model(["some-random:1b"]) == "some-random:1b"
    assert pick_ollama_model([]) is None


def test_upsert_env_creates_and_replaces(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    upsert_env(env, {"OPENAI_API_KEY": "k1", "MIDAS_MODEL_CHEAP": "openai/gpt-4o-mini"})
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=k1" in text
    assert "MIDAS_MODEL_CHEAP=openai/gpt-4o-mini" in text
    # Replace, not duplicate.
    upsert_env(env, {"OPENAI_API_KEY": "k2"})
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=k2" in text
    assert text.count("OPENAI_API_KEY=") == 1


def test_upsert_env_preserves_comments_and_other_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# my env\nFOO=bar\n", encoding="utf-8")
    upsert_env(env, {"OPENAI_API_KEY": "k"})
    text = env.read_text(encoding="utf-8")
    assert "# my env" in text
    assert "FOO=bar" in text
    assert "OPENAI_API_KEY=k" in text


def test_ensure_providers_yml_copies_example(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "providers.example.yml").write_text("roles: {}\n", encoding="utf-8")
    out = ensure_providers_yml(cfg)
    assert out.exists()
    assert out.name == "providers.yml"


def test_configure_with_key_writes_env(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.example.yml").write_text("roles: {}\n", encoding="utf-8")
    result = configure(tmp_path, key="sk-ant-secret123")
    assert result.mode == "cloud"
    assert result.provider == "anthropic"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=sk-ant-secret123" in env_text
    assert "MIDAS_MODEL_CHEAP=anthropic/" in env_text


def test_configure_unknown_key_returns_none_mode(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.example.yml").write_text("roles: {}\n", encoding="utf-8")
    result = configure(tmp_path, key="garbage-key-no-prefix")
    assert result.mode == "none"
    # No .env mutation for an unrecognized key.
    assert not (tmp_path / ".env").exists() or "garbage" not in (
        tmp_path / ".env"
    ).read_text(encoding="utf-8")


def test_configure_no_key_no_ollama_returns_none(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.example.yml").write_text("roles: {}\n", encoding="utf-8")
    # Force "no ollama".
    monkeypatch.setattr("midas.flagship.onboard.detect_ollama", lambda *a, **k: [])
    result = configure(tmp_path, key=None)
    assert result.mode == "none"


def test_configure_detects_local_ollama(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "providers.example.yml").write_text("roles: {}\n", encoding="utf-8")
    monkeypatch.setattr(
        "midas.flagship.onboard.detect_ollama", lambda *a, **k: ["llama3.1:8b"]
    )
    result = configure(tmp_path, key=None)
    assert result.mode == "local"
    assert result.model == "ollama/llama3.1:8b"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MIDAS_MODEL_CHEAP=ollama/llama3.1:8b" in env_text
