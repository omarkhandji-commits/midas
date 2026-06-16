"""WS4 — Heartbeat: gated in preparation only, hard caps, never executes."""

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
from midas.flagship.flows.cash_loop import CashLoop
from midas.flagship.flows.demo import demo_candidates
from midas.flagship.flows.heartbeat import CashHeartbeat


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
    ledger = ReceiptLedger(state / "receipts.jsonl", Signer.from_hex_seed("d4" * 32))
    approvals = ApprovalQueue(state / "apv.db", ledger=ledger)
    memory = MemoryStore(state / "mem.db")
    toolset = build_default_toolset(
        sentinel=sentinel, guard=guard, ledger=ledger, approvals=approvals, run_id="hb",
    )
    loop = CashLoop(toolset=toolset, memory=memory, ledger=ledger, approvals=approvals)
    return loop, approvals, workspace


def test_heartbeat_prepares_multiple_niches_all_gated(tmp_path: Path) -> None:
    loop, approvals, workspace = _build(tmp_path)
    hb = CashHeartbeat(loop=loop, max_niches=3, max_artifacts=10)
    cands = demo_candidates()
    report = hb.run_once(
        niches=["plumbers", "electricians", "cake-shops"],
        live=False,
        candidates_by_niche={
            "plumbers": cands, "electricians": cands, "cake-shops": cands,
        },
    )
    assert len(report.runs) == 3
    # Each niche queued at least one artifact (the landing draft).
    assert report.approvals_queued >= 3
    # Critical: NO file was written on disk.
    assert not list(workspace.glob("*.html"))
    # And every approval is pending — never auto-resolved.
    pending = approvals.pending()
    assert len(pending) >= 3


def test_heartbeat_respects_max_niches_cap(tmp_path: Path) -> None:
    loop, _, _ = _build(tmp_path)
    hb = CashHeartbeat(loop=loop, max_niches=1)
    cands = demo_candidates()
    report = hb.run_once(
        niches=["a", "b", "c"],
        live=False,
        candidates_by_niche={"a": cands, "b": cands, "c": cands},
    )
    assert len(report.runs) == 1  # cap respected


def test_heartbeat_respects_max_artifacts_cap(tmp_path: Path) -> None:
    loop, _, _ = _build(tmp_path)
    hb = CashHeartbeat(loop=loop, max_artifacts=1)
    cands = demo_candidates()
    report = hb.run_once(
        niches=["a", "b", "c"],
        live=False,
        candidates_by_niche={"a": cands, "b": cands, "c": cands},
    )
    # Stops mid-run because the cap fires before the 2nd niche.
    assert report.approvals_queued <= 2
    assert "max_artifacts" in report.stopped_reason or len(report.runs) <= 2


def test_heartbeat_skips_niches_without_candidates_when_offline(tmp_path: Path) -> None:
    loop, _, _ = _build(tmp_path)
    hb = CashHeartbeat(loop=loop)
    report = hb.run_once(niches=["unknown"], live=False, candidates_by_niche={})
    # No router + no candidates → 0 runs, no fabrication.
    assert len(report.runs) == 0
    assert report.approvals_queued == 0


def test_heartbeat_live_without_router_stops_cleanly(tmp_path: Path) -> None:
    loop, _, _ = _build(tmp_path)
    hb = CashHeartbeat(loop=loop, router=None)
    report = hb.run_once(niches=["plumbers"], live=True)
    assert "no router" in report.stopped_reason
    assert report.approvals_queued == 0


def test_heartbeat_empty_niches() -> None:
    # Build minimal — no need for paths.
    class _Toolset:
        def invoke(self, *a, **k):  # pragma: no cover - never called
            raise AssertionError("invoke must not be called")
    loop = CashLoop(toolset=_Toolset())
    hb = CashHeartbeat(loop=loop)
    report = hb.run_once(niches=[])
    assert report.stopped_reason == "no niches"
