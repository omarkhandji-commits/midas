"""Market Radar: competitor snapshots become sourced market memory + receipts."""

from __future__ import annotations

from pathlib import Path

from midas.core.memory import MemoryKind, MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.web import StaticFetcher
from midas.flagship.market import CompetitorStore


def test_competitor_watch_records_initial_and_changed_snapshot(tmp_path: Path) -> None:
    store = CompetitorStore(tmp_path / "market.db")
    mem = MemoryStore(tmp_path / "memory.db")
    ledger = ReceiptLedger(tmp_path / "receipts.jsonl", Signer.from_hex_seed("dd" * 32))
    comp = store.add("Acme", "https://acme.example/pricing")

    first = store.snapshot(
        comp,
        fetcher=StaticFetcher({"https://acme.example/pricing": "old price 49"}),
        memory=mem,
        ledger=ledger,
    )
    second = store.snapshot(
        comp,
        fetcher=StaticFetcher({"https://acme.example/pricing": "new price 79"}),
        memory=mem,
        ledger=ledger,
    )

    assert first.change_kind == "initial"
    assert second.change_kind == "changed"
    market = mem.recall(kind=MemoryKind.MARKET, query="Acme")
    assert market and "changed" in market[0].content
    assert [r.body.tool for r in ledger][-2:] == ["competitor.snapshot", "competitor.snapshot"]
