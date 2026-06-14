"""Business assets: heuristic drafts always work; LLM path is budgeted+receipted."""

from __future__ import annotations

from pathlib import Path

from midas.core.agents.summary import Finding, ProofLevel
from midas.core.budget import BudgetFuse, Caps, SpendStore
from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.router import ChatResult, LLMRouter
from midas.flagship.assets import ASSET_KEYS, heuristic_assets, llm_assets
from midas.flagship.flows import run_scan
from midas.flagship.flows.render import render_report
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores

STRONG = FactorScores(
    demand=9, speed_to_cash=8, mrr_potential=9, low_support=8, defensibility=6,
    low_competition=7, distribution=8, low_cost=9, low_launch_time=8, low_risk=8, operator_fit=8,
)


def _cand(name="Invoice chaser") -> OpportunityCandidate:
    return OpportunityCandidate(
        name=name, summary="follow-ups for trades",
        findings=[Finding("real pain", ProofLevel.HIGH, sources=["reddit.com/x"])],
        factors=STRONG,
    )


def test_heuristic_assets_always_produce_all_five() -> None:
    a = heuristic_assets(_cand())
    d = a.as_dict()
    assert set(d) == set(ASSET_KEYS)
    for v in d.values():
        assert v.strip()  # never empty


def test_scan_brief_now_carries_real_assets() -> None:
    report = run_scan("niche", [_cand()])
    assert report.daily_move is not None
    drafts = report.daily_move.brief.draft_assets
    assert "offer" in drafts and "outreach_email" in drafts
    assert "{{first_name}}" in drafts["outreach_email"]  # opt-in friendly placeholder
    script = drafts["video_script"].lower()
    assert "approval" in script or "approve" in script


def test_render_report_still_works_with_assets() -> None:
    report = run_scan("niche", [_cand()])
    text = render_report(report)
    # The renderer must not crash on the now-populated draft_assets dict.
    assert "DAILY REVENUE MOVE" in text
    assert "Invoice chaser" in text


# ── LLM-backed path: budgeted + receipted via the router ──────────────────────
def _router(text: str, **kw) -> LLMRouter:
    providers = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="m"), "smart": RoleConfig(primary="s")}
    )
    return LLMRouter(
        providers,
        complete_fn=lambda model, msgs: ChatResult(
            text=text, model=model, prompt_tokens=10, completion_tokens=10
        ),
        **kw,
    )


def test_llm_assets_use_router_for_every_asset(tmp_path: Path) -> None:
    calls = []

    def _fake(model, msgs):
        calls.append(msgs[-1]["content"])
        return ChatResult(text="DRAFTED", model=model, prompt_tokens=10, completion_tokens=10)

    providers = ProvidersConfig(roles={"cheap": RoleConfig(primary="m")})
    router = LLMRouter(providers, complete_fn=_fake)
    a = llm_assets(_cand(), router=router)
    assert len(calls) == len(ASSET_KEYS)  # one router call per asset
    for v in a.as_dict().values():
        assert v == "DRAFTED"


def test_llm_assets_fallback_to_heuristic_on_empty_text() -> None:
    # Model returns empty → fall back to deterministic heuristic, never an empty draft.
    router = _router("")
    a = llm_assets(_cand("Acme widget"), router=router)
    assert "Acme widget" in a.offer  # the heuristic kicked in


def test_llm_assets_are_budgeted_and_receipted(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("aa" * 32))
    fuse = BudgetFuse(SpendStore(tmp_path / "s.db"), Caps(per_task=1, daily=1, monthly=1))
    router = _router("DRAFTED", fuse=fuse, ledger=ledger, cost_fn=lambda m, p, c: 0.005)
    llm_assets(_cand(), router=router, task_id="t1")
    # 5 assets × one receipt each
    receipts = [r for r in ledger if r.body.tool == "llm.complete"]
    assert len(receipts) == len(ASSET_KEYS)
