"""LLM provider catalog and offline diagnostics.

MIDAS routes through LiteLLM-compatible model ids, but the product surface needs a
clear answer to "does my key/local model work?". This module keeps that answer
deterministic and testable without making network calls.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from midas.core.config.models import ProvidersConfig


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    api_key_env: str | None
    base_url_env: str | None = None
    local: bool = False
    notes: str = ""


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    local: bool
    missing: tuple[str, ...]
    notes: str


def catalog() -> dict[str, ProviderSpec]:
    specs = [
        ProviderSpec("openai", "OpenAI", "OPENAI_API_KEY"),
        ProviderSpec("anthropic", "Anthropic Claude", "ANTHROPIC_API_KEY"),
        ProviderSpec("google", "Google Gemini AI Studio", "GEMINI_API_KEY"),
        ProviderSpec("azure", "Azure OpenAI", "AZURE_API_KEY", "AZURE_API_BASE"),
        ProviderSpec("vertex", "Google Vertex AI", None, "VERTEX_PROJECT"),
        ProviderSpec("bedrock", "AWS Bedrock", None, "AWS_REGION"),
        ProviderSpec("mistral", "Mistral", "MISTRAL_API_KEY"),
        ProviderSpec("groq", "Groq", "GROQ_API_KEY"),
        ProviderSpec("together", "Together AI", "TOGETHER_API_KEY"),
        ProviderSpec("openrouter", "OpenRouter", "OPENROUTER_API_KEY"),
        ProviderSpec("deepseek", "DeepSeek", "DEEPSEEK_API_KEY"),
        ProviderSpec("cohere", "Cohere", "COHERE_API_KEY"),
        ProviderSpec("perplexity", "Perplexity", "PERPLEXITY_API_KEY"),
        ProviderSpec("xai", "xAI", "XAI_API_KEY"),
        ProviderSpec("cerebras", "Cerebras", "CEREBRAS_API_KEY"),
        ProviderSpec("fireworks", "Fireworks", "FIREWORKS_API_KEY"),
        ProviderSpec("replicate", "Replicate", "REPLICATE_API_TOKEN"),
        ProviderSpec("huggingface", "Hugging Face", "HUGGINGFACE_API_KEY"),
        ProviderSpec(
            "ollama",
            "Ollama local",
            None,
            "OLLAMA_BASE_URL",
            local=True,
            notes="Defaults to http://localhost:11434 when the env var is absent.",
        ),
        ProviderSpec("lm_studio", "LM Studio local", None, "LM_STUDIO_BASE_URL", local=True),
        ProviderSpec("vllm", "vLLM local/server", None, "VLLM_BASE_URL", local=True),
        ProviderSpec(
            "openai_compatible",
            "Any OpenAI-compatible endpoint",
            "OPENAI_COMPATIBLE_API_KEY",
            "OPENAI_COMPATIBLE_BASE_URL",
            notes="Use for custom gateways, proxies, or self-hosted APIs.",
        ),
    ]
    return {s.name: s for s in specs}


def diagnose_providers(
    config: ProvidersConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> list[ProviderStatus]:
    values = env if env is not None else os.environ
    specs = catalog()
    names = set(specs) | set(config.providers)
    statuses: list[ProviderStatus] = []

    for name in sorted(names):
        spec = specs.get(name)
        entry = config.providers.get(name)
        api_key_env = entry.api_key_env if entry and entry.api_key_env else (
            spec.api_key_env if spec else None
        )
        base_url_env = entry.base_url_env if entry and entry.base_url_env else (
            spec.base_url_env if spec else None
        )
        local = bool(spec.local) if spec else False

        missing: list[str] = []
        if api_key_env and not values.get(api_key_env):
            missing.append(api_key_env)
        if base_url_env and not values.get(base_url_env) and not (name == "ollama"):
            missing.append(base_url_env)

        configured = not missing and (local or bool(api_key_env or base_url_env or entry))
        statuses.append(
            ProviderStatus(
                name=name,
                configured=configured,
                local=local,
                missing=tuple(missing),
                notes=(spec.notes if spec else "Custom provider from providers.yml."),
            )
        )
    return statuses


def render_provider_example(name: str) -> str:
    spec = catalog().get(name)
    if spec is None:
        return (
            f"{name}:\n"
            "  api_key_env: CUSTOM_API_KEY\n"
            "  base_url_env: CUSTOM_BASE_URL\n"
        )
    lines = [f"{spec.name}:"]
    if spec.api_key_env:
        lines.append(f"  api_key_env: {spec.api_key_env}")
    if spec.base_url_env:
        lines.append(f"  base_url_env: {spec.base_url_env}")
    if len(lines) == 1:
        lines.append("  # no key required")
    return "\n".join(lines) + "\n"
