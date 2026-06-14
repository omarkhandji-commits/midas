"""LLM router: cascade, escalation, fallback, budget integration, and the council."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.budget import BudgetExceeded, BudgetFuse, Caps, SpendStore
from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.core.router import ChatResult, Council, LLMRouter, RouterError, estimate_cost


def _providers() -> ProvidersConfig:
    return ProvidersConfig(
        roles={
            "cheap": RoleConfig(primary="ollama/llama3.1", fallbacks=["groq/llama-3.1-8b"]),
            "smart": RoleConfig(primary="anthropic/claude-sonnet", fallbacks=["openai/gpt-4.1"]),
        }
    )


def _fake(table: dict[str, str]):
    def fn(model: str, messages):
        if model not in table:
            raise RuntimeError(f"no such model: {model}")
        return ChatResult(text=table[model], model=model, prompt_tokens=100, completion_tokens=50)

    return fn


MSG = [{"role": "user", "content": "hi"}]


def test_picks_cheap_primary() -> None:
    r = LLMRouter(_providers(), complete_fn=_fake({"ollama/llama3.1": "cheap"}))
    res = r.complete(MSG, role="cheap")
    assert res.model == "ollama/llama3.1" and res.text == "cheap"


def test_escalates_to_smart() -> None:
    r = LLMRouter(_providers(), complete_fn=_fake({"anthropic/claude-sonnet": "smart"}))
    res = r.complete(MSG, role="cheap", escalate=True)
    assert res.model == "anthropic/claude-sonnet"


def test_fallback_when_primary_fails() -> None:
    r = LLMRouter(_providers(), complete_fn=_fake({"groq/llama-3.1-8b": "fallback"}))
    res = r.complete(MSG, role="cheap")
    assert res.model == "groq/llama-3.1-8b"


def test_all_models_fail_raises() -> None:
    r = LLMRouter(_providers(), complete_fn=_fake({}))
    with pytest.raises(RouterError):
        r.complete(MSG, role="cheap")


def test_budget_blocks_before_call(tmp_path: Path) -> None:
    fuse = BudgetFuse(
        SpendStore(tmp_path / "s.db"),
        Caps(per_task=0.001, daily=0.001, monthly=0.001),
    )
    r = LLMRouter(_providers(), fuse=fuse, complete_fn=_fake({"ollama/llama3.1": "x"}))
    with pytest.raises(BudgetExceeded):
        r.complete(MSG, role="cheap", est_usd=0.05, task_id="t1")


def test_commits_actual_cost(tmp_path: Path) -> None:
    store = SpendStore(tmp_path / "s.db")
    fuse = BudgetFuse(store, Caps(per_task=1.0, daily=1.0, monthly=1.0))
    r = LLMRouter(
        _providers(),
        fuse=fuse,
        complete_fn=_fake({"ollama/llama3.1": "x"}),
        cost_fn=lambda m, p, c: 0.02,
    )
    r.complete(MSG, role="cheap", est_usd=0.01, task_id="t1")
    assert abs(store.total(task_id="t1") - 0.02) < 1e-9


def test_unknown_model_priced_expensive() -> None:
    assert estimate_cost("ollama/llama3.1", 1000, 1000) == 0.0
    assert estimate_cost("some/unknown", 1000, 1000) > 0.0  # fail expensive-safe


def test_council_agreement_no_escalation() -> None:
    r = LLMRouter(
        _providers(),
        complete_fn=_fake({"m1": "same", "m2": "same", "m3": "same", "chair": "final"}),
    )
    council = Council(r, members=["m1", "m2", "m3"], chairman="chair")
    res = council.deliberate(MSG)
    assert res.agreement == 1.0
    assert res.escalate_to_human is False
    assert res.final.text == "final"


def test_council_disagreement_escalates_to_human() -> None:
    r = LLMRouter(
        _providers(),
        complete_fn=_fake({"m1": "A", "m2": "B", "m3": "C", "chair": "final"}),
    )
    council = Council(r, members=["m1", "m2", "m3"], chairman="chair", agreement_threshold=0.5)
    res = council.deliberate(MSG)
    assert res.agreement < 0.5
    assert res.escalate_to_human is True  # disagreement = signal to ask a human
