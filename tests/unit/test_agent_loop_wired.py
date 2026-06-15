"""Stream E3 — AgentLoop with research tool wired + autoskills detection."""

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
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel import Sentinel
from midas.core.web import StaticFetcher, StaticSearchAdapter
from midas.core.web.search import SearchHit
from midas.flagship.agent import AgentLoop, build_default_toolset
from midas.flagship.agent.loop import AgentTranscript
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.autoskills import AutoSkills, AutoSkillsStore
from midas.flagship.skills import SkillRegistry


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


def test_research_run_tool_returns_proof_and_sources(tmp_path: Path) -> None:
    search = StaticSearchAdapter([
        SearchHit(title="A", url="https://a.example/p"),
        SearchHit(title="B", url="https://b.example/p"),
        SearchHit(title="C", url="https://c.example/p"),
    ])
    fetcher = StaticFetcher({
        "https://a.example/p": "alpha",
        "https://b.example/p": "beta",
        "https://c.example/p": "gamma",
    })
    sentinel = Sentinel(_policy())
    guard = FsGuard(workspace=tmp_path.resolve())
    toolset = build_default_toolset(
        sentinel=sentinel, guard=guard, search=search, fetcher=fetcher, run_id="r"
    )
    out = toolset.invoke("research.run", question="topic", k=3)
    assert out.ran is True
    assert out.value["proof_level"] == "high"  # 3 reachable → HIGH per D2 contract
    assert out.value["verified_count"] == 3
    assert len(out.value["sources"]) == 3


def test_autoskills_detect_runs_on_finished_loop_receipts(tmp_path: Path) -> None:
    state = tmp_path / ".midas"
    state.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ledger = ReceiptLedger(state / "r.jsonl", Signer.from_hex_seed("e3" * 32))
    queue = ApprovalQueue(state / "apv.db", ledger=ledger)
    sentinel = Sentinel(_policy())
    guard = FsGuard(workspace=workspace.resolve())
    toolset = build_default_toolset(
        sentinel=sentinel, guard=guard, ledger=ledger, approvals=queue, run_id="t-do"
    )
    # Seed a 3-step purely-local AGENT RUN (3 fs.list / fs.read calls).
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    def _planner(task: str, transcript: AgentTranscript):  # noqa: ARG001
        if len(transcript.steps) == 0:
            return {"tool": "fs.list", "inputs": {"path": "."}}
        if len(transcript.steps) == 1:
            return {"tool": "fs.read", "inputs": {"path": "a.txt"}}
        if len(transcript.steps) == 2:
            return {"tool": "fs.read", "inputs": {"path": "a.txt", "max_chars": 100}}
        return {"done": True, "summary": "ok"}

    loop = AgentLoop(toolset=toolset, planner=_planner, max_steps=5)
    t = loop.run("read")
    assert t.stopped_reason == "ok"
    # 3 ALLOWed reads on the same run_id → AutoSkills must propose ONE skill.
    store = AutoSkillsStore(state / "autoskills.json")
    registry = SkillRegistry(state)
    auto = AutoSkills(
        registry=registry, ledger=ledger, queue=queue, store=store, search=None
    )
    proposals = auto.detect()
    assert len(proposals) == 1
    # fs.read emits UNTRUSTED taint (file contents are data); that correctly bars
    # silent auto-accept for any sequence that includes file reads. The proposal
    # still surfaces — it just requires an approval before becoming a real skill.
    assert proposals[0].local_only is False
    assert len(proposals[0].steps) >= 3


def test_research_tool_omitted_when_no_search_adapter(tmp_path: Path) -> None:
    sentinel = Sentinel(_policy())
    guard = FsGuard(workspace=tmp_path.resolve())
    toolset = build_default_toolset(sentinel=sentinel, guard=guard, run_id="x")
    assert "research.run" not in toolset.names
