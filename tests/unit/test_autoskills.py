"""Sprint D1 — Auto-skills detection, accept/discard, multi-source discovery.

Invariants under test:
- A 3+ step ALLOWed run produces a proposal; local-only proposals can auto-accept.
- A run that included an approval (QUEUE_APPROVAL) is NOT local-only and cannot
  auto-accept — it must go through ApprovalQueue (existing security model).
- Multi-source tool discovery uses `site:` filters across multiple registries,
  not GitHub alone.
- Every accept / discard / remote-plan writes a receipt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.approvals.queue import ApprovalQueue
from midas.core.receipts.ledger import ReceiptLedger
from midas.core.receipts.models import Decision, Taint
from midas.core.receipts.signer import Signer
from midas.core.web.search import SearchHit, StaticSearchAdapter
from midas.flagship.autoskills import (
    DEFAULT_DISCOVERY_SOURCES,
    AutoSkills,
    AutoSkillsStore,
)
from midas.flagship.skills import SkillRegistry


def _build(tmp_path: Path) -> AutoSkills:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("a1" * 32))
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    registry = SkillRegistry(tmp_path)
    store = AutoSkillsStore(tmp_path / "autoskills.json")
    search = StaticSearchAdapter(
        [
            SearchHit(title="trafilatura on PyPI", url="https://pypi.org/project/trafilatura/",
                     snippet="extractor"),
            SearchHit(title="trafilatura on npm", url="https://www.npmjs.com/package/trafilatura",
                     snippet="js port"),
        ]
    )
    return AutoSkills(
        registry=registry, ledger=ledger, queue=queue, store=store, search=search
    )


def _run_three_local_steps(ledger: ReceiptLedger, run_id: str) -> None:
    for tool in ("research.search", "research.fetch", "research.summarize"):
        ledger.append(
            run_id=run_id,
            agent="researcher",
            tool=tool,
            decision=Decision.ALLOW,
            inputs={"step": tool},
            outputs={"ok": True},
            taint_in=Taint.TRUSTED,
            taint_out=Taint.TRUSTED,
        )


def test_detect_proposes_skill_for_three_step_allow_sequence(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    _run_three_local_steps(auto._ledger, "run-A")  # noqa: SLF001

    proposals = auto.detect()
    assert len(proposals) == 1
    p = proposals[0]
    assert p.local_only is True
    assert p.status == "pending"
    assert len(p.steps) == 3


def test_detect_is_idempotent_for_same_run_id(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    _run_three_local_steps(auto._ledger, "run-B")  # noqa: SLF001
    first = auto.detect()
    second = auto.detect()
    assert len(first) == 1
    assert second == []


def test_accept_local_proposal_creates_skill_and_writes_receipt(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    _run_three_local_steps(auto._ledger, "run-C")  # noqa: SLF001
    [p] = auto.detect()
    manifest = auto.accept(p.proposal_id)

    assert manifest.name.startswith("auto-")
    assert manifest.source == "local-created"
    saved = auto._store.get(p.proposal_id)  # noqa: SLF001
    assert saved is not None and saved.status == "accepted"
    tools = {r.body.tool for r in auto._ledger}  # noqa: SLF001
    assert "autoskills.accept" in tools


def test_non_local_proposal_cannot_auto_accept(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    ledger = auto._ledger  # noqa: SLF001
    # First step looks like a remote fetch that returned UNTRUSTED content.
    ledger.append(
        run_id="run-D",
        agent="researcher",
        tool="web.fetch",
        decision=Decision.ALLOW,
        inputs={"url": "https://example.com"},
        outputs={"len": 100},
        taint_in=Taint.TRUSTED,
        taint_out=Taint.UNTRUSTED,
    )
    for tool in ("research.summarize", "memory.store"):
        ledger.append(
            run_id="run-D",
            agent="researcher",
            tool=tool,
            decision=Decision.ALLOW,
            inputs={},
            outputs={},
        )

    [p] = auto.detect()
    assert p.local_only is False
    with pytest.raises(PermissionError):
        auto.accept(p.proposal_id)


def test_propose_remote_queues_approval_and_writes_receipt(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    ledger = auto._ledger  # noqa: SLF001
    ledger.append(
        run_id="run-E",
        agent="researcher",
        tool="web.fetch",
        decision=Decision.ALLOW,
        inputs={},
        outputs={},
        taint_in=Taint.TRUSTED,
        taint_out=Taint.UNTRUSTED,
    )
    for tool in ("research.summarize", "memory.store"):
        ledger.append(run_id="run-E", agent="r", tool=tool,
                      decision=Decision.ALLOW, inputs={}, outputs={})

    [p] = auto.detect()
    req = auto.propose_remote(
        p.proposal_id,
        url="https://github.com/example/skill.git",
        rationale="need trafilatura wrapper",
    )
    assert req.id is not None
    pending = auto._queue.pending()  # noqa: SLF001
    assert any(r.id == req.id for r in pending)
    decisions = {r.body.decision.value for r in ledger}
    assert "queue_approval" in decisions


def test_propose_remote_rejects_local_url(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    _run_three_local_steps(auto._ledger, "run-F")  # noqa: SLF001
    [p] = auto.detect()
    with pytest.raises(ValueError, match="not a remote source"):
        auto.propose_remote(p.proposal_id, url="/local/path", rationale="oops")


def test_discover_tool_queries_all_sources_not_just_github(tmp_path: Path) -> None:
    calls: list[str] = []

    class _SpyAdapter:
        def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
            calls.append(query)
            return [SearchHit(title="x", url="https://example.com/x")]

    auto = _build(tmp_path)
    auto._search = _SpyAdapter()  # noqa: SLF001
    auto.discover_tool("trafilatura")

    # Every registry in the default set must be queried, AND github cannot be the
    # only source the auto-skills layer trusts.
    assert len(calls) == len(DEFAULT_DISCOVERY_SOURCES)
    assert any("pypi.org" in c for c in calls)
    assert any("registry.npmjs.org" in c for c in calls)
    assert any("crates.io" in c for c in calls)
    assert any("mcp.so" in c for c in calls) or any(
        "modelcontextprotocol.io" in c for c in calls
    )
    # github is included, but it is one of many — not the only one.
    github_calls = [c for c in calls if "github.com" in c]
    assert len(github_calls) == 1
    assert len(github_calls) < len(calls)


def test_sequence_ending_in_deny_is_not_proposed(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    ledger = auto._ledger  # noqa: SLF001
    for tool in ("research.search", "research.fetch"):
        ledger.append(run_id="run-G", agent="r", tool=tool,
                      decision=Decision.ALLOW, inputs={}, outputs={})
    ledger.append(run_id="run-G", agent="r", tool="email.send",
                  decision=Decision.DENY, inputs={}, outputs={})

    assert auto.detect() == []


def test_discard_marks_proposal_and_writes_receipt(tmp_path: Path) -> None:
    auto = _build(tmp_path)
    _run_three_local_steps(auto._ledger, "run-H")  # noqa: SLF001
    [p] = auto.detect()
    auto.discard(p.proposal_id, reason="not useful")
    saved = auto._store.get(p.proposal_id)  # noqa: SLF001
    assert saved is not None and saved.status == "discarded"
    tools = {r.body.tool for r in auto._ledger}  # noqa: SLF001
    assert "autoskills.discard" in tools
