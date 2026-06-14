"""Render a ScanReport as plain text for the CLI (the Daily Revenue Move on top)."""

from __future__ import annotations

from midas.flagship.opportunity import ScanReport

_PROOF_BADGE = {"high": "Proof: HIGH", "medium": "Proof: MED", "low": "Proof: LOW"}


def render_report(report: ScanReport) -> str:
    lines: list[str] = []
    lines.append(f"MIDAS scan - niche: {report.niche}")
    lines.append("=" * 60)

    move = report.daily_move
    if move is None:
        lines.append("DAILY REVENUE MOVE: (abstained)")
        lines.append(f"  reason: {report.abstained_reason}")
    else:
        c = move.candidate
        lines.append("DAILY REVENUE MOVE")
        lines.append(f"  {c.name}")
        lines.append(f"  {c.summary}")
        lines.append(
            f"  score: {move.breakdown.total:.1f}/100  band: {move.breakdown.band.value}  "
            f"[{_PROOF_BADGE[move.proof_level.value]}]"
        )
        lines.append(f"  sources: {', '.join(c.sources) or '(none)'}")
        lines.append("  prepared:")
        for step in move.brief.steps:
            lines.append(f"    - {step}")
        lines.append("  estimate (NOT a prediction):")
        lines.append(
            f"    ~{move.estimate.est_time_hours:.0f}h, ~${move.estimate.est_cost_usd:.2f}; "
            f"assumptions: {'; '.join(move.estimate.assumptions)}"
        )
        gate = "requires your approval" if move.next_action_requires_approval else "auto"
        lines.append(f"  next action ({gate}): {move.next_action}")

    lines.append("-" * 60)
    lines.append("Shortlist:")
    for s in report.shortlist:
        lines.append(
            f"  [{s.breakdown.total:5.1f}] {s.band.value:9} "
            f"{_PROOF_BADGE[s.candidate.proof_level.value]:11} {s.candidate.name}"
        )

    lines.append("-" * 60)
    lines.append(f"Spent this run: ${report.spent_usd:.4f} (from receipts)")
    lines.append("No revenue is promised. You approve and execute every outbound action.")
    return "\n".join(lines)
