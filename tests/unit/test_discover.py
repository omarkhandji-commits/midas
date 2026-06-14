"""Discover: strict-JSON parsing, Proof-First clamping, and the wired scan_niche flow."""

from __future__ import annotations

import json
from pathlib import Path

from midas.core.agents.summary import ProofLevel
from midas.core.budget import BudgetFuse, Caps, SpendStore
from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.router import ChatResult, LLMRouter
from midas.flagship.flows import parse_candidates, scan_niche

_FACTORS = {
    "demand": 9, "speed_to_cash": 8, "mrr_potential": 9, "low_support": 8, "defensibility": 6,
    "low_competition": 7, "distribution": 8, "low_cost": 9, "low_launch_time": 8, "low_risk": 8,
    "operator_fit": 8,
}


def _payload(**over) -> str:
    cand = {
        "name": "Invoice chaser",
        "summary": "follow-ups for trades",
        "findings": [{"claim": "real pain", "proof_level": "high", "sources": ["reddit.com/x"]}],
        "factors": _FACTORS,
        "gates": {},
    }
    cand.update(over)
    return json.dumps({"candidates": [cand]})


def _router(text: str, **kw) -> LLMRouter:
    providers = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="m"), "smart": RoleConfig(primary="s")}
    )
    return LLMRouter(
        providers,
        complete_fn=lambda model, msgs: ChatResult(
            text=text, model=model, prompt_tokens=20, completion_tokens=10
        ),
        **kw,
    )


# ── parsing / proof-first ────────────────────────────────────────────────────
def test_parses_valid_candidates() -> None:
    cands = parse_candidates(_payload())
    assert len(cands) == 1
    assert cands[0].name == "Invoice chaser"
    assert cands[0].proof_level == ProofLevel.HIGH


def test_unsourced_high_claim_is_downgraded_to_low() -> None:
    # Model claims HIGH but cites nothing → clamped to LOW (no asserting evidence it lacks).
    cands = parse_candidates(
        _payload(findings=[{"claim": "trust me", "proof_level": "high", "sources": []}])
    )
    assert cands[0].proof_level == ProofLevel.LOW


def test_candidate_with_no_findings_is_dropped() -> None:
    assert parse_candidates(_payload(findings=[])) == []


def test_garbage_text_yields_no_candidates() -> None:
    assert parse_candidates("the model rambled and forgot the JSON") == []


def test_tolerates_json_fences_and_prose() -> None:
    wrapped = "Sure! Here you go:\n```json\n" + _payload() + "\n```\nHope that helps."
    assert len(parse_candidates(wrapped)) == 1


# ── wired flow: discover → score → daily move, budgeted + receipted ──────────
def test_scan_niche_produces_move_and_receipts_cost(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("cd" * 32))
    fuse = BudgetFuse(SpendStore(tmp_path / "s.db"), Caps(per_task=1, daily=1, monthly=1))
    router = _router(_payload(), fuse=fuse, ledger=ledger, cost_fn=lambda m, p, c: 0.01)

    report = scan_niche(
        "tools for plumbers", router=router, ledger=ledger, task_id="t1", est_usd=0.005
    )

    assert report.daily_move is not None
    assert report.daily_move.candidate.name == "Invoice chaser"
    assert report.spent_usd > 0  # cost read back from the receipts ledger
    assert any(r.body.tool == "llm.complete" for r in ledger)
