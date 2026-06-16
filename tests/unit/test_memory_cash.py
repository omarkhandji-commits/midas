"""WS3 — Cash namespace + bias_kind: additive, Proof-First, rétro-compatible."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.agents.summary import ProofLevel
from midas.core.memory import MemoryKind, MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "mem.db")


def test_record_cash_low_proof_without_sources(tmp_path: Path) -> None:
    m = _store(tmp_path)
    e = m.record_cash(
        "kenza-sweets:cold-email",
        channel="cold-email",
        offer="custom-cakes-mtl",
        revenue_usd=150.0,
        cost_usd=12.50,
    )
    assert e.kind == MemoryKind.CASH
    assert e.proof_level == ProofLevel.LOW
    assert "net=$137.50" in e.content
    assert "cash" in e.tags


def test_record_cash_medium_proof_with_sources(tmp_path: Path) -> None:
    m = _store(tmp_path)
    e = m.record_cash(
        "agency:upsell",
        channel="dm",
        offer="seo-audit",
        revenue_usd=500.0,
        cost_usd=0.0,
        sources=["https://stripe.com/receipt/abc123"],
    )
    assert e.proof_level == ProofLevel.MEDIUM
    assert e.sources == ["https://stripe.com/receipt/abc123"]


def test_recall_by_cash_kind(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.record_cash("a", channel="x", offer="y", revenue_usd=10, cost_usd=1)
    m.record_cash("b", channel="z", offer="w", revenue_usd=20, cost_usd=2)
    cash = m.recall(kind=MemoryKind.CASH)
    assert len(cash) == 2
    # Other namespaces are unaffected.
    assert m.recall(kind=MemoryKind.USER) == []


def test_context_pack_default_unchanged(tmp_path: Path) -> None:
    """Rétro-compat: appel sans bias_kind = comportement actuel."""
    m = _store(tmp_path)
    m.remember(MemoryKind.USER, "name", "Omar")
    m.record_cash("a", channel="cold-email", offer="cake", revenue_usd=100, cost_usd=5)
    pack = m.context_pack()
    # USER vient avant CASH dans l'ordre déclaré de l'enum.
    user_pos = pack.find("## USER")
    cash_pos = pack.find("## CASH")
    assert user_pos != -1 and cash_pos != -1
    assert user_pos < cash_pos


def test_context_pack_bias_to_cash_puts_cash_first(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.remember(MemoryKind.USER, "name", "Omar")
    m.record_cash("a", channel="cold-email", offer="cake", revenue_usd=100, cost_usd=5)
    pack = m.context_pack(bias_kind=MemoryKind.CASH)
    user_pos = pack.find("## USER")
    cash_pos = pack.find("## CASH")
    assert cash_pos != -1 and user_pos != -1
    assert cash_pos < user_pos, "bias_kind=CASH should surface cash section first"


def test_context_pack_bias_kind_with_no_cash_entries_does_not_crash(
    tmp_path: Path,
) -> None:
    m = _store(tmp_path)
    m.remember(MemoryKind.USER, "name", "Omar")
    pack = m.context_pack(bias_kind=MemoryKind.CASH)
    # Pas de CASH dans la base → la section n'apparait simplement pas.
    assert "## CASH" not in pack
    assert "## USER" in pack


def test_record_cash_supersede_keeps_history(tmp_path: Path) -> None:
    m = _store(tmp_path)
    m.record_cash("k", channel="cold-email", offer="cake", revenue_usd=50, cost_usd=10)
    m.record_cash("k", channel="cold-email", offer="cake", revenue_usd=200, cost_usd=10)
    live = m.recall(kind=MemoryKind.CASH)
    assert len(live) == 1 and "$200.00" in live[0].content
    hist = m.history(MemoryKind.CASH, "k")
    assert [e.superseded for e in hist] == [True, False]


def test_proof_first_invariant_on_cash(tmp_path: Path) -> None:
    """Forcer HIGH sans source doit refuser comme pour tout autre kind."""
    m = _store(tmp_path)
    with pytest.raises(ValueError):
        m.remember(
            MemoryKind.CASH,
            "k",
            "claim",
            proof_level=ProofLevel.HIGH,
        )
