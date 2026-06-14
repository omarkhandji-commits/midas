"""Provider-agnostic LLM router: role-based cascade (cheap→smart), budgeted, receipted.

The actual provider call is a pluggable `complete_fn(model, messages) -> ChatResult`
(default: LiteLLM, imported lazily). Tests inject a fake — no API key needed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from midas.core.config.models import ProvidersConfig
from midas.core.receipts.models import Decision

from .cost import estimate_cost
from .models import ChatResult

Messages = list[dict[str, Any]]
CompleteFn = Callable[[str, Messages], ChatResult]
CostFn = Callable[[str, int, int], float]


class RouterError(Exception):
    pass


def _redact(messages: Messages) -> list[dict[str, Any]]:
    # never store raw message content in receipts — only shape
    return [{"role": m.get("role"), "len": len(str(m.get("content", "")))} for m in messages]


def _default_litellm_complete(model: str, messages: Messages) -> ChatResult:
    import litellm  # lazy: only needed for real calls

    resp = litellm.completion(model=model, messages=messages)
    text = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    pt = getattr(usage, "prompt_tokens", 0) if usage else 0
    ct = getattr(usage, "completion_tokens", 0) if usage else 0
    try:
        cost: Optional[float] = float(litellm.completion_cost(completion_response=resp))
    except Exception:
        cost = None
    return ChatResult(text=text, model=model, prompt_tokens=pt, completion_tokens=ct, cost_usd=cost)


class LLMRouter:
    def __init__(
        self,
        providers: ProvidersConfig,
        *,
        fuse: Any = None,  # core.budget.BudgetFuse (optional)
        ledger: Any = None,  # core.receipts.ReceiptLedger (optional)
        complete_fn: Optional[CompleteFn] = None,
        cost_fn: Optional[CostFn] = None,
    ) -> None:
        self.providers = providers
        self.fuse = fuse
        self.ledger = ledger
        self._complete_fn = complete_fn or _default_litellm_complete
        self._cost_fn = cost_fn or estimate_cost

    def _models_for_role(self, role: str) -> list[str]:
        rc = self.providers.roles.get(role)
        if rc is None:
            raise RouterError(f"unknown model role: {role!r}")
        return [rc.primary, *rc.fallbacks]

    def complete(
        self,
        messages: Messages,
        *,
        role: str = "cheap",
        escalate: bool = False,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        est_usd: float = 0.0,
        agent: str = "router",
    ) -> ChatResult:
        models = self._models_for_role("smart" if escalate else role)
        return self._run(models, messages, task_id=task_id, run_id=run_id, est_usd=est_usd, agent=agent)

    def complete_model(
        self,
        model: str,
        messages: Messages,
        *,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        est_usd: float = 0.0,
        agent: str = "router",
    ) -> ChatResult:
        return self._run([model], messages, task_id=task_id, run_id=run_id, est_usd=est_usd, agent=agent)

    def _run(
        self,
        models: list[str],
        messages: Messages,
        *,
        task_id: Optional[str],
        run_id: Optional[str],
        est_usd: float,
        agent: str,
    ) -> ChatResult:
        # Reserve the estimated cost BEFORE making any call (may raise BudgetExceeded).
        if self.fuse is not None:
            self.fuse.check(est_usd, task_id=task_id)

        last_exc: Optional[Exception] = None
        for model in models:
            try:
                res = self._complete_fn(model, messages)
            except Exception as exc:  # noqa: BLE001 - try next model in the cascade
                last_exc = exc
                continue
            if res.cost_usd is None:
                res.cost_usd = self._cost_fn(res.model or model, res.prompt_tokens, res.completion_tokens)
            if self.fuse is not None:
                self.fuse.commit(
                    res.cost_usd, run_id=run_id, task_id=task_id, kind="llm", model=res.model or model
                )
            if self.ledger is not None:
                self.ledger.append(
                    run_id=run_id or "",
                    agent=agent,
                    tool="llm.complete",
                    decision=Decision.ALLOW,
                    inputs={"model": model, "messages": _redact(messages)},
                    outputs={"text_len": len(res.text)},
                    cost_usd=res.cost_usd,
                )
            return res
        raise RouterError(f"all models failed: {models}") from last_exc
