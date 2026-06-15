"""Sprint F4 — ROI ledger + Proof Link export."""

from __future__ import annotations

import json
import re
from pathlib import Path

from midas.core.memory import MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision, Taint
from midas.flagship.proof_link import export_proof_link
from midas.flagship.roi import (
    build_outcomes_index,
    compute_run_roi,
    format_roi_report,
)


def test_roi_report_groups_by_run_and_joins_outcome(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f4" * 32))
    # Two runs: one with a recorded outcome, one without.
    for cost in (0.01, 0.02):
        ledger.append(
            run_id="run-A", agent="a", tool="t",
            decision=Decision.ALLOW, inputs={}, outputs={}, cost_usd=cost,
        )
    ledger.append(
        run_id="run-B", agent="a", tool="t",
        decision=Decision.ALLOW, inputs={}, outputs={}, cost_usd=0.05,
    )
    memory = MemoryStore(":memory:")
    memory.record_result(
        "run-A", outcome="signed", metrics={"revenue": 1000.0}, sources=["client@email"]
    )

    report = compute_run_roi(ledger, build_outcomes_index(memory))
    run_a = next(r for r in report.runs if r.run_id == "run-A")
    run_b = next(r for r in report.runs if r.run_id == "run-B")
    assert run_a.cost_usd == 0.03
    assert run_a.revenue_usd == 1000.0
    assert run_a.net_usd == 999.97
    assert run_a.roi_ratio is not None and run_a.roi_ratio > 30000
    assert run_a.receipt_count == 2
    # No outcome → revenue=0; no fabricated number.
    assert run_b.revenue_usd == 0.0
    assert run_b.roi_ratio is not None  # cost>0, revenue=0 ⇒ ratio=0
    assert report.total_cost == 0.08
    assert report.total_revenue == 1000.0


def test_roi_never_invents_revenue_for_unrecorded_run(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f4" * 32))
    ledger.append(
        run_id="lonely", agent="a", tool="t",
        decision=Decision.ALLOW, inputs={}, outputs={}, cost_usd=0.5,
    )
    report = compute_run_roi(ledger, build_outcomes_index(MemoryStore(":memory:")))
    [row] = report.runs
    assert row.revenue_usd == 0.0
    assert row.sources == []


def test_roi_format_includes_disclaimer_when_runs_exist(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f4" * 32))
    ledger.append(
        run_id="r1", agent="a", tool="t",
        decision=Decision.ALLOW, inputs={}, outputs={}, cost_usd=0.01,
    )
    text = format_roi_report(compute_run_roi(ledger, {}))
    assert "TOTAL" in text
    assert "No projections" in text


def test_roi_format_handles_empty_report() -> None:
    text = format_roi_report(compute_run_roi([], {}))
    assert "No runs yet" in text


# ── Proof Links ───────────────────────────────────────────────────────────────


def test_proof_link_contains_full_chain(tmp_path: Path) -> None:
    signer = Signer.from_hex_seed("aa" * 32)
    ledger = ReceiptLedger(tmp_path / "r.jsonl", signer)
    for i in range(3):
        ledger.append(
            run_id="proof-run", agent="a", tool="t",
            decision=Decision.ALLOW, inputs={"i": i}, outputs={},
            taint_in=Taint.TRUSTED, taint_out=Taint.TRUSTED,
        )
    html = export_proof_link(ledger, public_key_hex=signer.public_key_hex)
    assert "<!doctype html>" in html
    # Receipts json embedded.
    assert "proof-run" in html
    # Public key surfaced in the document.
    assert signer.public_key_hex in html
    # The verifier code runs in the browser — text we know is there.
    assert "Verifying chain" in html


def test_proof_link_filtered_by_run_id(tmp_path: Path) -> None:
    signer = Signer.from_hex_seed("ab" * 32)
    ledger = ReceiptLedger(tmp_path / "r.jsonl", signer)
    ledger.append(run_id="a", agent="x", tool="t",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    ledger.append(run_id="b", agent="x", tool="t",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    html = export_proof_link(ledger, public_key_hex=signer.public_key_hex, run_id="a")
    # Extract embedded JSON to assert the filter.
    match = re.search(
        r'<script id="payload" type="application/json">(.+?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert all(r["body"]["run_id"] == "a" for r in payload)
    assert len(payload) == 1


def test_proof_link_verifier_does_not_import_midas(tmp_path: Path) -> None:
    """The HTML must verify offline — no midas.* import path anywhere in it."""
    signer = Signer.from_hex_seed("ac" * 32)
    ledger = ReceiptLedger(tmp_path / "r.jsonl", signer)
    ledger.append(run_id="r", agent="x", tool="t",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    html = export_proof_link(ledger, public_key_hex=signer.public_key_hex)
    # The verifier is fully inline; no remote script tags.
    assert "<script src=" not in html
    # No reference to the python verifier path.
    assert "midas_verify" not in html
    assert "midas." not in html.lower().replace("midas proof link", "")
