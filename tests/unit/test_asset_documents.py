"""Business Workbench document exports."""

from __future__ import annotations

from pathlib import Path

from midas.core.agents.summary import Finding, ProofLevel
from midas.flagship.assets import ASSET_KEYS, heuristic_assets, write_asset_files
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores


def _candidate() -> OpportunityCandidate:
    return OpportunityCandidate(
        name="Invoice chaser",
        summary="follow-ups for trades",
        findings=[Finding("real pain", ProofLevel.HIGH, sources=["https://src.example"])],
        factors=FactorScores(**{k: 7 for k in FactorScores.model_fields}),
    )


def test_asset_set_includes_business_workbench_outputs() -> None:
    assets = heuristic_assets(_candidate()).as_dict()
    for key in (
        "proposal_pdf",
        "invoice_pdf",
        "call_script",
        "objection_handling",
        "followup_sequence",
        "action_plan_7d",
    ):
        assert key in ASSET_KEYS
        assert assets[key].strip()


def test_write_asset_files_creates_real_pdfs(tmp_path: Path) -> None:
    written = write_asset_files(heuristic_assets(_candidate()), tmp_path)
    assert written["proposal_pdf"].suffix == ".pdf"
    assert written["invoice_pdf"].read_bytes().startswith(b"%PDF-1.4")
    assert written["offer"].read_text(encoding="utf-8").startswith("# One-page offer")
