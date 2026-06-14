"""Agents layer: Sentinel-wrapped toolset, isolated subagents, single supervisor.

The headline guarantee tested here: a tool is unreachable except through the toolset,
and the Sentinel — not the model — decides whether it runs. DENY and QUEUE_APPROVAL
both mean the underlying callable never executes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.agents import (
    DispatchResult,
    Finding,
    ProofLevel,
    Subagent,
    Supervisor,
    Tool,
    ToolDenied,
    Toolset,
)
from midas.core.budget.loop_breaker import LoopBreaker
from midas.core.config import load_policy
from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.core.receipts import ReceiptLedger, Signer, verify_chain
from midas.core.receipts.models import Decision, Taint
from midas.core.router import ChatResult, LLMRouter
from midas.core.sentinel import Sentinel

BASE = Path(__file__).resolve().parents[2]


def _toolset(tmp_path: Path, **overrides) -> tuple[Toolset, ReceiptLedger]:
    policy = load_policy(BASE / "config" / "policy.yml")
    if overrides:
        policy = policy.model_copy(update=overrides)
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("44" * 32))
    return Toolset(Sentinel(policy), ledger=ledger, run_id="run1"), ledger


# ── toolset / security invariant ─────────────────────────────────────────────
def test_auto_tool_runs_and_is_receipted(tmp_path: Path) -> None:
    ts, ledger = _toolset(tmp_path)
    ts.register(Tool("search", action="web_search", fn=lambda **k: "results"))
    out = ts.invoke("search", q="x")
    assert out.ran is True and out.value == "results"
    assert verify_chain(ledger.path, ledger.public_key_hex).ok
    assert list(ledger)[-1].body.decision == Decision.ALLOW


def test_approval_tool_does_not_run(tmp_path: Path) -> None:
    ts, _ = _toolset(tmp_path)
    fired = []
    ts.register(Tool("email", action="send_email", fn=lambda **k: fired.append(1)))
    out = ts.invoke("email", to="a@b.com")
    assert out.ran is False
    assert out.verdict.needs_approval
    assert fired == []  # parked for a human; the callable never executed


def test_trifecta_tool_denied_and_never_runs(tmp_path: Path) -> None:
    ts, ledger = _toolset(tmp_path)
    fired = []
    ts.register(
        Tool(
            "exfil",
            action="send_email",
            fn=lambda **k: fired.append(1),
            has_private_access=True,
            has_egress=True,
            egress_domains=["evil.com"],
        )
    )
    with pytest.raises(ToolDenied):
        ts.invoke("exfil", input_taints={Taint.UNTRUSTED, Taint.PRIVATE}, body="secret")
    assert fired == []
    assert list(ledger)[-1].body.decision == Decision.DENY


def test_unknown_tool_default_denied(tmp_path: Path) -> None:
    ts, _ = _toolset(tmp_path)
    with pytest.raises(ToolDenied):
        ts.invoke("nope")


def test_duplicate_registration_rejected(tmp_path: Path) -> None:
    ts, _ = _toolset(tmp_path)
    ts.register(Tool("a", action="web_search", fn=lambda **k: 1))
    with pytest.raises(ValueError):
        ts.register(Tool("a", action="web_search", fn=lambda **k: 2))


# ── summary / proof-first ────────────────────────────────────────────────────
def test_sourced_claim_required_for_medium_or_high() -> None:
    Finding("ok", ProofLevel.HIGH, sources=["https://x"])  # fine
    with pytest.raises(ValueError):
        Finding("unsourced", ProofLevel.MEDIUM)  # no sources → rejected


def test_result_proof_level_is_weakest_finding() -> None:
    from midas.core.agents import SubagentResult

    r = SubagentResult(
        role="scout",
        findings=[
            Finding("a", ProofLevel.HIGH, sources=["s1"]),
            Finding("b", ProofLevel.LOW),
        ],
    )
    assert r.proof_level == ProofLevel.LOW
    assert r.sources == ["s1"]


# ── subagent isolation + escalation ──────────────────────────────────────────
def _router(text: str) -> LLMRouter:
    providers = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="m"), "smart": RoleConfig(primary="s")}
    )
    return LLMRouter(
        providers,
        complete_fn=lambda model, msgs: ChatResult(
            text=text, model=model, prompt_tokens=10, completion_tokens=5
        ),
    )


def test_subagent_returns_summary_with_findings() -> None:
    sub = Subagent(
        "scout",
        router=_router("raw model rambling"),
        parser=lambda t: [Finding("real pain", ProofLevel.HIGH, sources=["reddit.com/x"])],
    )
    res = sub.run("find pains in niche")
    assert res.role == "scout"
    assert res.proof_level == ProofLevel.HIGH
    assert res.escalated is False
    assert res.tokens == 15


def test_subagent_escalates_when_no_sourceable_finding() -> None:
    sub = Subagent("scout", router=_router("nothing"), parser=lambda t: [])
    res = sub.run("find pains")
    assert res.escalated is True
    assert res.proof_level == ProofLevel.LOW


# ── supervisor orchestration ─────────────────────────────────────────────────
def _parses(level: ProofLevel, src: str = "s"):
    return lambda t: [Finding("p", level, sources=[src])]


def test_supervisor_collects_isolated_summaries() -> None:
    sup = Supervisor(run_id="run1")
    sup.add(
        Subagent("scout", router=_router("x"), parser=_parses(ProofLevel.HIGH)),
        "scout the niche",
    )
    sup.add(
        Subagent("market", router=_router("y"), parser=_parses(ProofLevel.MEDIUM, "s2")),
        "size the market",
    )
    out: DispatchResult = sup.dispatch(task_id="t1")
    assert [r.role for r in out.results] == ["scout", "market"]
    assert out.overall_proof_level == ProofLevel.MEDIUM  # weakest contributor
    assert out.stopped_reason is None


def test_supervisor_loop_breaker_stops_runaway() -> None:
    sup = Supervisor(loop_breaker=LoopBreaker(max_iterations=1), run_id="run1")
    for i in range(5):
        sup.add(
            Subagent(f"a{i}", router=_router("x"), parser=_parses(ProofLevel.HIGH)),
            "work",
        )
    out = sup.dispatch()
    assert out.stopped_reason is not None
    assert len(out.results) < 5  # broke early
