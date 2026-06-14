"""The scan flow writes its decision into memory (closes the Track loop)."""

from __future__ import annotations

from pathlib import Path

from midas.core.agents.summary import Finding, ProofLevel
from midas.core.memory import MemoryKind, MemoryStore
from midas.flagship.flows import run_scan
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores

STRONG = FactorScores(
    demand=9, speed_to_cash=8, mrr_potential=9, low_support=8, defensibility=6,
    low_competition=7, distribution=8, low_cost=9, low_launch_time=8, low_risk=8, operator_fit=8,
)


def _cand(name: str, sourced: bool = True) -> OpportunityCandidate:
    findings = (
        [Finding(f"pain for {name}", ProofLevel.HIGH, sources=["reddit.com/x"])]
        if sourced else []
    )
    return OpportunityCandidate(name=name, summary="...", findings=findings, factors=STRONG)


def test_scan_logs_decision_when_move_chosen(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    report = run_scan("plumbers", [_cand("primary"), _cand("alt1"), _cand("alt2")], memory=mem)
    assert report.daily_move is not None
    decisions = mem.recall(kind=MemoryKind.DECISION, query="scan:plumbers")
    assert decisions
    content = decisions[0].content
    assert "Chose: primary" in content
    assert "alt1" in content and "alt2" in content  # rejected alternates recorded
    assert "proven" in content  # the "why" line names proof status


def test_scan_logs_abstention(tmp_path: Path) -> None:
    mem = MemoryStore(tmp_path / "m.db")
    run_scan("plumbers", [_cand("weak", sourced=False)], memory=mem)
    decisions = mem.recall(kind=MemoryKind.DECISION, query="scan:plumbers")
    assert decisions and "abstained" in decisions[0].content
