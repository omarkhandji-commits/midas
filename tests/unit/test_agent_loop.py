"""AgentLoop — gated execution via Toolset + receipt + approval pause."""

from __future__ import annotations

from pathlib import Path

from midas.core.agents import Tool, Toolset
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
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision, Taint
from midas.core.sentinel import Sentinel
from midas.flagship.agent import AgentLoop, build_default_toolset
from midas.flagship.agent.loop import AgentTranscript
from midas.flagship.agent.tools.fsguard import FsGuard


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files", "build_local_files"},
            requires_approval={"repo_write", "execute_code"},
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


def _setup(tmp_path: Path) -> tuple[Path, ReceiptLedger, ApprovalQueue, AgentLoop]:
    state = tmp_path / ".midas"
    state.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = ReceiptLedger(state / "r.jsonl", Signer.from_hex_seed("a4" * 32))
    queue = ApprovalQueue(state / "apv.db", ledger=ledger)
    sentinel = Sentinel(_policy())
    guard = FsGuard(workspace=workspace.resolve())
    toolset = build_default_toolset(
        sentinel=sentinel, guard=guard, ledger=ledger, approvals=queue, run_id="t-run"
    )

    # Seed a readable file.
    (workspace / "report.txt").write_text("hello report", encoding="utf-8")
    return workspace, ledger, queue, AgentLoop(
        toolset=toolset, planner=_stub_planner, max_steps=5
    )


# Deterministic planner — encodes a 3-step plan: read → write → done.
def _stub_planner(task: str, transcript: AgentTranscript):  # noqa: ARG001
    n = len(transcript.steps)
    if n == 0:
        return {"tool": "fs.read", "inputs": {"path": "report.txt"}}
    if n == 1:
        return {"tool": "fs.write", "inputs": {"path": "summary.txt", "content": "summary"}}
    return {"done": True, "summary": "done"}


def test_loop_runs_read_inline_and_queues_write_approval(tmp_path: Path) -> None:
    workspace, ledger, queue, loop = _setup(tmp_path)
    t = loop.run("summarize report.txt")
    assert t.steps[0].tool == "fs.read"
    assert t.steps[0].decision == "allow"
    assert t.steps[0].ran is True
    # Step 2 is fs.write → APPROVE-tier; queued, not run, loop pauses.
    assert t.steps[1].tool == "fs.write"
    assert t.steps[1].decision == "queue_approval"
    assert t.steps[1].ran is False
    assert t.steps[1].approval_id is not None
    # The file MUST NOT exist yet.
    assert not (workspace / "summary.txt").exists()
    # Loop paused at the approval; planner was never asked again after step 2.
    assert len(t.steps) == 2
    assert "awaiting approval" in (t.stopped_reason or "")
    # Receipt ledger reflects the queue_approval verdict.
    decisions = [r.body.decision for r in ledger]
    assert Decision.QUEUE_APPROVAL in decisions


def test_execute_approved_step_writes_file_and_writes_receipt(tmp_path: Path) -> None:
    workspace, ledger, queue, loop = _setup(tmp_path)
    transcript = loop.run("write summary")
    apv_id = transcript.queued_approvals[0]
    queue.approve(apv_id, by="test")

    # Now execute the gated step using the same machinery the CLI uses.
    from midas.flagship.agent.execute import execute_approved_step

    class _RT:
        def __init__(self, ledger, queue, guard):
            self.ledger = ledger
            self.approvals = queue
            self.fs_guard = guard

            class _Append:
                def __init__(_self, ledger_):
                    _self.ledger = ledger_

                def __call__(_self, **kwargs):
                    _self.ledger.append(**kwargs)

            self.append_receipt = _Append(ledger)

    runtime = _RT(ledger, queue, FsGuard(workspace=workspace.resolve()))
    request = queue.get(apv_id)
    out = execute_approved_step(runtime, request)
    assert (workspace / "summary.txt").read_text(encoding="utf-8") == "summary"
    assert out["bytes_len"] == 7
    tools = {r.body.tool for r in ledger}
    assert "fs.write.executed" in tools


def test_loop_max_steps_bounds_iterations(tmp_path: Path) -> None:
    _, _, _, loop_ = _setup(tmp_path)

    def _never_done(task: str, transcript: AgentTranscript):  # noqa: ARG001
        return {"tool": "fs.list", "inputs": {"path": "."}}

    loop_._planner = _never_done  # noqa: SLF001
    t = loop_.run("loop forever")
    # max_steps=5 in setup → exactly 5 fs.list steps then stopped.
    assert len(t.steps) == 5
    assert t.stopped_reason == "max_steps reached"


def test_loop_unknown_tool_denied_by_toolset(tmp_path: Path) -> None:
    _, _, _, loop_ = _setup(tmp_path)

    def _ask_unknown(task: str, transcript: AgentTranscript):  # noqa: ARG001
        return {"tool": "no.such.tool", "inputs": {}}

    loop_._planner = _ask_unknown  # noqa: SLF001
    t = loop_.run("rogue")
    assert t.steps[0].decision == "deny"
    assert "no.such.tool" in (t.steps[0].error or "")


def test_loop_propagates_untrusted_taint_to_later_tools(tmp_path: Path) -> None:
    policy = _policy().model_copy(update={"egress_allowlist": ["api.good.test"]})
    toolset = Toolset(Sentinel(policy))
    toolset.register(
        Tool(
            "read.untrusted",
            action="read_local_files",
            fn=lambda: {"text": "web data"},
            output_taint=Taint.UNTRUSTED,
        )
    )
    toolset.register(
        Tool(
            "private.egress",
            action="read_local_files",
            fn=lambda: {"ok": True},
            has_private_access=True,
            has_egress=True,
            egress_domains=["api.good.test"],
        )
    )

    def _plan(task: str, transcript: AgentTranscript):  # noqa: ARG001
        if not transcript.steps:
            return {"tool": "read.untrusted", "inputs": {}}
        return {"tool": "private.egress", "inputs": {}}

    loop = AgentLoop(toolset=toolset, planner=_plan, max_steps=3)
    transcript = loop.run("try exfil")
    assert transcript.steps[0].decision == "allow"
    assert transcript.steps[0].output_taint == Taint.UNTRUSTED.value
    assert transcript.steps[1].decision == "deny"
    assert "lethal trifecta" in (transcript.steps[1].error or "")
