"""Memory store: six namespaces, supersede-keeps-history, recall, Proof-First, context pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.agents.summary import ProofLevel
from midas.core.memory import MemoryKind, MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "mem.db")


def test_remember_and_recall_by_kind(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.remember(MemoryKind.USER, "budget", "operator caps spend at $2/day")
    m.remember(MemoryKind.BUSINESS, "offer", "sells a $29/mo invoice helper")
    assert len(m.recall(kind=MemoryKind.USER)) == 1
    assert m.recall(kind=MemoryKind.BUSINESS)[0].content.startswith("sells")


def test_update_supersedes_but_keeps_history(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.remember(MemoryKind.BUSINESS, "price", "price is $19/mo")
    m.remember(MemoryKind.BUSINESS, "price", "price is $29/mo")
    live = m.recall(kind=MemoryKind.BUSINESS)
    assert len(live) == 1 and "29" in live[0].content  # only the live version
    hist = m.history(MemoryKind.BUSINESS, "price")
    assert [e.superseded for e in hist] == [True, False]  # old kept, marked superseded
    assert "19" in hist[0].content


def test_proof_first_medium_needs_source(tmp_path: Path) -> None:
    m = _store(tmp_path)
    with pytest.raises(ValueError):
        m.remember(MemoryKind.MARKET, "rival", "rival raised prices", proof_level=ProofLevel.HIGH)
    ok = m.remember(
        MemoryKind.MARKET, "rival", "rival raised to $39", proof_level=ProofLevel.HIGH,
        sources=["competitor.com/pricing"],
    )
    assert ok.proof_level == ProofLevel.HIGH


def test_decision_memory_records_chose_and_rejected(tmp_path: Path) -> None:
    m = _store(tmp_path)
    e = m.record_decision(
        "channel", chose="Telegram", rejected=["WhatsApp", "email"], why="lowest API friction"
    )
    assert e.kind == MemoryKind.DECISION
    assert "Telegram" in e.content and "WhatsApp" in e.content and "friction" in e.content


def test_result_and_error_memory(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.record_result(
        "launch1", outcome="3 signups", metrics={"clicks": 120}, sources=["dash.local/x"]
    )
    err = m.record_error(
        "cold-dm", what_failed="mass DM outreach", why="flagged as spam, 0 replies"
    )
    assert m.recall(tag="track")[0].proof_level == ProofLevel.MEDIUM  # sourced result
    assert err.kind == MemoryKind.ERROR
    assert m.recall(kind=MemoryKind.ERROR, query="spam")  # the lesson is findable


def test_context_pack_bundles_live_memories(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.remember(MemoryKind.USER, "style", "prefers concise, no hype")
    m.record_error("ads", what_failed="paid ads", why="CAC too high")
    pack = m.context_pack(per_kind=2)
    assert "## USER" in pack and "## ERROR" in pack
    assert "no hype" in pack and "CAC too high" in pack
