"""Cost estimation (USD). Unknown models are priced as 'smart' — fail expensive-safe."""

from __future__ import annotations

# (input_usd_per_1M, output_usd_per_1M) — coarse table; LiteLLM refines real costs at runtime.
_PRICES: dict[str, tuple[float, float]] = {
    "ollama/llama3.1": (0.0, 0.0),
    "groq/llama-3.1-8b": (0.05, 0.08),
    "mistral/mistral-small": (0.20, 0.60),
    "together/Nous-Hermes": (0.20, 0.20),
    "anthropic/claude-sonnet": (3.0, 15.0),
    "openai/gpt-4.1": (2.0, 8.0),
}

# An unknown model is assumed expensive so a mis-routed call never silently overspends.
_UNKNOWN_PRICE = (3.0, 15.0)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = _PRICES.get(model, _UNKNOWN_PRICE)
    return prompt_tokens / 1_000_000 * pin + completion_tokens / 1_000_000 * pout
