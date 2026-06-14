"""P&L: costs are summed from the (verifiable) receipts ledger, not self-reported."""

from __future__ import annotations

import tempfile
from pathlib import Path

from midas.core.receipts import Decision, ReceiptLedger, Signer
from midas.flagship.pnl import compute_pnl


def _ledger() -> ReceiptLedger:
    path = Path(tempfile.mkdtemp()) / "receipts.jsonl"
    return ReceiptLedger(path, Signer.from_hex_seed("33" * 32))


def test_cost_is_summed_from_receipts() -> None:
    led = _ledger()
    for c in (0.01, 0.02, 0.03):
        led.append(
            run_id="r",
            agent="router",
            tool="llm.complete",
            decision=Decision.ALLOW,
            inputs={},
            outputs={},
            cost_usd=c,
        )
    pnl = compute_pnl(led, revenue_usd=0.0)
    assert abs(pnl.cost_usd - 0.06) < 1e-9


def test_net_is_revenue_minus_cost() -> None:
    led = _ledger()
    led.append(
        run_id="r",
        agent="router",
        tool="llm.complete",
        decision=Decision.ALLOW,
        inputs={},
        outputs={},
        cost_usd=0.10,
    )
    pnl = compute_pnl(led, revenue_usd=5.00)
    assert abs(pnl.net_usd - 4.90) < 1e-9
