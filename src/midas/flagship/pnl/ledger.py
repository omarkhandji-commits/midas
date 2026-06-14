"""Live P&L. Costs come straight from the receipts ledger (verifiable, not self-reported)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from midas.core.receipts.models import Receipt


@dataclass
class PnL:
    cost_usd: float
    revenue_usd: float

    @property
    def net_usd(self) -> float:
        return round(self.revenue_usd - self.cost_usd, 6)


def compute_pnl(receipts: Iterable[Receipt], revenue_usd: float = 0.0) -> PnL:
    """Sum receipted costs (the dashboard cost meter reads this)."""
    cost = sum(r.body.cost_usd for r in receipts)
    return PnL(cost_usd=round(cost, 6), revenue_usd=round(revenue_usd, 6))
