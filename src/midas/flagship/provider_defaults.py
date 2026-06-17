"""Shared defaults for provider → cheap-role model mapping.

Mutualised between ``onboard.py`` (CLI ``midas init``) and ``provider_settings.py``
(dashboard ``POST /api/providers``) so a key entered through either surface lands
on the same model and the agent works immediately — no silent dead-end where the
key is stored but the role still points elsewhere.
"""

from __future__ import annotations

# Provider name (lowercase, matches `providers.example.yml`) → LiteLLM-style
# default model id used as the ``cheap`` role primary when the user only gives us
# an API key. Conservative picks: cheap, broadly available, no surprise pricing.
DEFAULT_CHEAP_MODEL: dict[str, str] = {
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-3-5-haiku-latest",
    "openrouter": "openrouter/auto",
    "groq": "groq/llama-3.1-8b-instant",
    "google": "gemini/gemini-1.5-flash",
}


def cheap_model_for(provider: str) -> str | None:
    """Return the default cheap model for a provider name, or ``None`` if unknown.

    Case-insensitive; ``-`` and ``_`` are interchangeable.
    """
    name = provider.strip().lower().replace("-", "_")
    return DEFAULT_CHEAP_MODEL.get(name)


__all__ = ["DEFAULT_CHEAP_MODEL", "cheap_model_for"]
