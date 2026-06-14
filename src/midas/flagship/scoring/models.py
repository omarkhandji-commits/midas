"""Scoring models: per-factor inputs (0..10), hard gates, and the breakdown output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

_F = Field(ge=0, le=10)


class FactorScores(BaseModel):
    demand: float = _F
    speed_to_cash: float = _F
    mrr_potential: float = _F
    low_support: float = _F
    defensibility: float = _F
    low_competition: float = _F
    distribution: float = _F
    low_cost: float = _F
    low_launch_time: float = _F
    low_risk: float = _F
    operator_fit: float = _F


class HardGates(BaseModel):
    """Any True gate forces ARCHIVE regardless of score (see docs/SCORING.md)."""

    requires_deception: bool = False  # spam / lies / guaranteed-income claims
    legally_gray_or_pii: bool = False
    structurally_high_support: bool = False
    no_distribution_channel: bool = False


class Band(str, Enum):
    BUILD = "BUILD"
    WATCHLIST = "WATCHLIST"
    ARCHIVE = "ARCHIVE"


@dataclass
class ScoreBreakdown:
    total: float
    band: Band
    contributions: dict[str, float]
    weakest_factor: str
    archived_by_gate: Optional[str] = None
