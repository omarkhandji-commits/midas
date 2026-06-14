"""Eval suite: harness primitives, the five concrete evals, and report rendering."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from midas.core.eval import CaseResult, Eval, render_report
from midas.flagship.cli import app
from midas.flagship.eval import build_suite

BASE = Path(__file__).resolve().parents[2]
runner = CliRunner()


# ── harness primitives ───────────────────────────────────────────────────────
def test_eval_threshold_passes() -> None:
    e = Eval("ok", "", lambda: [
        CaseResult("a", True, 1, 1),
        CaseResult("b", True, 2, 2),
    ])
    r = e.execute()
    assert r.verdict == "pass" and r.rate == 1.0


def test_eval_threshold_fails_below() -> None:
    e = Eval("partial", "", lambda: [
        CaseResult("a", True, 1, 1),
        CaseResult("b", False, 1, 2),
    ], threshold=1.0)
    r = e.execute()
    assert r.verdict == "fail" and r.passed == 1


def test_eval_partial_threshold_passes_when_met() -> None:
    e = Eval("partial-ok", "", lambda: [
        CaseResult("a", True, 1, 1),
        CaseResult("b", False, 1, 2),
    ], threshold=0.5)
    r = e.execute()
    assert r.verdict == "pass"


# ── concrete suite is deterministic and passes ───────────────────────────────
def test_full_suite_passes_clean_checkout() -> None:
    """If THIS test ever fails it means a Proof-First invariant has regressed."""
    suite = build_suite(BASE / "config" / "policy.yml")
    results = suite.run()
    assert {r.eval_name for r in results} == {
        "fake-source clamping", "unsourced model claims", "budget fuse",
        "lethal trifecta", "context compression fidelity", "asset quality",
        "operator autonomy guardrails",
    }
    for r in results:
        assert r.verdict == "pass", f"{r.eval_name} failed: {[c for c in r.cases if not c.passed]}"


def test_suite_is_deterministic() -> None:
    """Two consecutive runs produce identical pass/fail patterns."""
    suite = build_suite(BASE / "config" / "policy.yml")
    a = [(r.eval_name, [c.passed for c in r.cases]) for r in suite.run()]
    b = [(r.eval_name, [c.passed for c in r.cases]) for r in suite.run()]
    assert a == b


# ── report rendering ─────────────────────────────────────────────────────────
def test_report_includes_verdicts_and_cases() -> None:
    results = build_suite(BASE / "config" / "policy.yml").run()
    text = render_report(results)
    assert text.startswith("# MIDAS Transparency Report")
    assert "Overall: **PASS**" in text  # the bundled suite is green
    for r in results:
        assert f"## {r.eval_name}" in text  # per-eval section exists
    # No marketing claims, no revenue promise.
    assert "guarantee" not in text.lower()
    assert "promise" not in text.lower()


# ── CLI smoke ────────────────────────────────────────────────────────────────
def test_cli_eval_prints_report_and_exits_zero() -> None:
    result = runner.invoke(app, ["eval", "--base-dir", str(BASE)])
    assert result.exit_code == 0, result.stdout
    assert "Transparency Report" in result.stdout
    assert "**PASS**" in result.stdout


def test_cli_eval_writes_to_out(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    result = runner.invoke(app, ["eval", "--out", str(out), "--base-dir", str(BASE)])
    assert result.exit_code == 0
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# MIDAS Transparency Report")
