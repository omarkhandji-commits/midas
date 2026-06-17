"""One-command onboarding — make the first run work with zero friction.

`midas init` resolves an LLM in this order:

1. ``--key <APIKEY>`` provided  → detect the provider from the key prefix,
   write the key to ``.env``, point the cheap role at that provider.
2. A local Ollama server is reachable → pick an installed model, point the
   cheap role at it. No key needed.
3. Neither → print the two ways to get running.

It then writes ``config/providers.yml`` (from the example if missing) and runs
a one-token smoke test so "it works" is proven, not assumed.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from midas.flagship.provider_defaults import DEFAULT_CHEAP_MODEL

_OLLAMA_DEFAULT = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class KeyProfile:
    provider: str
    env_var: str
    model: str  # LiteLLM-style id for the cheap role


# Order matters: more specific prefixes first. The model id comes from the
# shared table in ``provider_defaults`` so the dashboard's ``add provider`` flow
# resolves to the same default.
def provider_from_key(key: str) -> KeyProfile | None:
    """Map an API key to (provider, env var, default cheap model) by prefix."""
    k = key.strip()
    if k.startswith("sk-ant-"):
        return KeyProfile("anthropic", "ANTHROPIC_API_KEY", DEFAULT_CHEAP_MODEL["anthropic"])
    if k.startswith("sk-or-"):
        return KeyProfile("openrouter", "OPENROUTER_API_KEY", DEFAULT_CHEAP_MODEL["openrouter"])
    if k.startswith("gsk_"):
        return KeyProfile("groq", "GROQ_API_KEY", DEFAULT_CHEAP_MODEL["groq"])
    if k.startswith("sk-proj-") or k.startswith("sk-"):
        return KeyProfile("openai", "OPENAI_API_KEY", DEFAULT_CHEAP_MODEL["openai"])
    if k.startswith("AIza"):
        return KeyProfile("google", "GEMINI_API_KEY", DEFAULT_CHEAP_MODEL["google"])
    return None


def detect_ollama(base_url: str = _OLLAMA_DEFAULT, *, timeout: float = 2.0) -> list[str]:
    """Return installed Ollama model names, or [] if the server is unreachable."""
    try:
        import httpx

        resp = httpx.get(f"{base_url}/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 — any failure means "no local Ollama"
        return []
    return [str(m.get("name")) for m in (data.get("models") or []) if m.get("name")]


def pick_ollama_model(models: list[str]) -> str | None:
    """Prefer a small general model for the cheap role; else first available."""
    preferred = ("llama3.1", "llama3", "qwen2.5", "mistral", "gemma", "phi")
    for needle in preferred:
        for m in models:
            if needle in m.lower():
                return m
    return models[0] if models else None


def upsert_env(env_path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value lines in ``.env``, replacing existing keys, creating the file."""
    lines: list[str] = []
    seen: set[str] = set()
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(raw)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_providers_yml(config_dir: Path) -> Path:
    """Create config/providers.yml from the example if it does not exist."""
    providers = config_dir / "providers.yml"
    example = config_dir / "providers.example.yml"
    if not providers.exists() and example.exists():
        shutil.copyfile(example, providers)
    return providers


@dataclass
class InitResult:
    mode: str           # "local" | "cloud" | "none"
    model: str = ""
    provider: str = ""
    detail: str = ""


def configure(base_dir: Path, *, key: str | None) -> InitResult:
    """Resolve an LLM and write config. Does NOT run the smoke test (caller does)."""
    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    ensure_providers_yml(config_dir)
    env_path = base_dir / ".env"

    # 1) Explicit key wins.
    if key:
        profile = provider_from_key(key)
        if profile is None:
            return InitResult(
                mode="none",
                detail="Unrecognized API key prefix. Set it manually in .env.",
            )
        upsert_env(
            env_path,
            {profile.env_var: key, "MIDAS_MODEL_CHEAP": profile.model},
        )
        return InitResult(mode="cloud", model=profile.model, provider=profile.provider)

    # 2) Local Ollama.
    models = detect_ollama()
    chosen = pick_ollama_model(models)
    if chosen:
        upsert_env(
            env_path,
            {
                "OLLAMA_BASE_URL": _OLLAMA_DEFAULT,
                "MIDAS_MODEL_CHEAP": f"ollama/{chosen}",
            },
        )
        return InitResult(mode="local", model=f"ollama/{chosen}", provider="ollama")

    # 3) Nothing usable.
    return InitResult(mode="none")


__all__ = [
    "KeyProfile",
    "InitResult",
    "provider_from_key",
    "detect_ollama",
    "pick_ollama_model",
    "upsert_env",
    "ensure_providers_yml",
    "configure",
]
