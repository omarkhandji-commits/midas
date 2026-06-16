"""WS1 — Cash loop: closed loop, gated, ROI cites receipts only."""

from __future__ import annotations

from pathlib import Path

from midas.core.approvals.queue import ApprovalQueue
from midas.core.config.models import (
    ActionsPolicy,
    ApprovalPolicy,
    AuditPolicy,
    FilesystemPolicy,
    ModelsPolicy,
    PolicyConfig,
    SourcesPolicy,
    SpendCaps,
)
from midas.core.memory import MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel import Sentinel
from midas.flagship.agent.registry import build_default_toolset
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.flows.attribution import link_outcome_to_run, move_key_for_run
from midas.flagship.flows.cash_loop import CashLoop
from midas.flagship.flows.demo import demo_candidates
from midas.flagship.flows.feedback import (
    FeedbackAdjustment,
    apply_feedback,
    feedback_factors,
)
from midas.flagship.scoring import FactorScores


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write", "execute_code", "write_spreadsheet"},
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


def _build(tmp_path: Path):
    state = tmp_path / ".midas"
    state.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    guard = FsGuard(workspace=workspace.resolve())
    sentinel = Sentinel(_policy())
    ledger = ReceiptLedger(state / "receipts.jsonl", Signer.from_hex_seed("c1" * 32))
    approvals = ApprovalQueue(state / "apv.db", ledger=ledger)
    memory = MemoryStore(state / "mem.db")
    toolset = build_default_toolset(
        sentinel=sentinel,
        guard=guard,
        ledger=ledger,
        approvals=approvals,
        run_id="t",
    )
    loop = CashLoop(toolset=toolset, memory=memory, ledger=ledger, approvals=approvals)
    return loop, ledger, approvals, memory, workspace


# ── attribution ───────────────────────────────────────────────────────────────


def test_attribution_key_equals_run_id() -> None:
    assert move_key_for_run("scan:abc") == "scan:abc"


def test_link_outcome_to_run_uses_run_id_as_move_key(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "m.db")
    link_outcome_to_run(
        memory,
        run_id="scan:plumbers",
        outcome="closed 1 invoice",
        metrics={"revenue": 250.0},
        sources=["https://stripe.com/r/abc"],
    )
    from midas.core.memory import MemoryKind

    rows = memory.recall(kind=MemoryKind.RESULT)
    assert len(rows) == 1
    assert rows[0].key == "scan:plumbers"
    assert "revenue=250" in rows[0].content


# ── feedback edge ────────────────────────────────────────────────────────────


def test_feedback_zero_without_memory() -> None:
    adj = feedback_factors(None)
    assert adj.is_zero


def test_feedback_positive_when_past_cash_was_a_win(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path / "m.db")
    memory.record_cash("a", channel="cold-email", offer="cake", revenue_usd=200, cost_usd=5)
    adj = feedback_factors(memory)
    assert not adj.is_zero
    assert adj.deltas.get("distribution", 0) > 0
    assert adj.deltas.get("speed_to_cash", 0) > 0


def test_feedback_apply_clamps_to_zero_ten() -> None:
    factors = FactorScores(
        demand=10, speed_to_cash=10, mrr_potential=5, low_support=5,
        defensibility=5, low_competition=5, distribution=10, low_cost=5,
        low_launch_time=5, low_risk=5, operator_fit=5,
    )
    adj = FeedbackAdjustment(deltas={"distribution": 2.0, "speed_to_cash": 2.0}, reasons=[])
    new = apply_feedback(factors, adj)
    # Already at 10 — clamp keeps them at 10, not 12.
    assert new.distribution == 10
    assert new.speed_to_cash == 10


# ── closed loop ───────────────────────────────────────────────────────────────


def test_cash_loop_scan_prepares_landing_and_queues_approval(tmp_path: Path) -> None:
    loop, ledger, approvals, memory, workspace = _build(tmp_path)
    report = loop.run("invoice-tools", candidates=demo_candidates())
    assert report.move is not None, "demo candidates should yield a move"
    assert len(report.artifacts) == 1
    art = report.artifacts[0]
    assert art.tool == "landing.draft"
    assert art.approval_id is not None  # queued, not run
    assert art.summary == "queued"
    # CRITICAL: no file was written.
    assert not list(workspace.glob("*.html"))


def test_cash_loop_pipeline_reflects_pending_then_outcome(tmp_path: Path) -> None:
    loop, ledger, approvals, memory, workspace = _build(tmp_path)
    loop.run("invoice-tools", candidates=demo_candidates())
    pipeline_before = loop.pipeline()
    # Must contain our pending approval row.
    pending_rows = [r for r in pipeline_before if r["stage"] == "awaiting_approval"]
    assert pending_rows, "pipeline should surface the awaiting approval"

    # Now operator records an outcome under THE SAME run_id used by the approval.
    run_ids = {r.run_id for r in approvals.pending()}
    assert run_ids
    rid = next(iter(run_ids))
    link_outcome_to_run(
        memory,
        run_id=rid,
        outcome="ship + first sale",
        metrics={"revenue": 100.0},
        sources=["https://stripe.com/r/x"],
    )
    pipeline_after = loop.pipeline()
    outcomed = [r for r in pipeline_after if r["run_id"] == rid]
    assert outcomed, f"run {rid} should appear in pipeline"
    assert outcomed[0]["stage"] == "outcome_recorded"
    assert outcomed[0]["revenue_usd"] == 100.0


def test_cash_loop_pipeline_roi_only_from_receipts(tmp_path: Path) -> None:
    """ROI totals row must aggregate from receipts only, never invent revenue."""
    loop, ledger, approvals, memory, workspace = _build(tmp_path)
    loop.run("invoice-tools", candidates=demo_candidates())
    pipeline = loop.pipeline()
    totals = [r for r in pipeline if r["run_id"] == "__totals__"]
    assert totals
    t = totals[0]
    # Without any recorded outcome → revenue = 0 (never invented).
    assert t["revenue_usd"] == 0.0
