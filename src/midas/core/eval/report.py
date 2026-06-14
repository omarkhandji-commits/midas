"""Transparency Report — what we publish instead of a self-scored benchmark.

The report is markdown so it travels well (PR descriptions, GitHub README sections,
audit submissions). It states:
  - what was measured;
  - the exact threshold;
  - per-case expected vs actual (auditable);
  - whether the run passed.

No prose, no marketing language. The reader gets the facts and can rerun any line.
"""

from __future__ import annotations

from .harness import EvalResult


def render_report(results: list[EvalResult], *, title: str = "MIDAS Transparency Report") -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    overall = "PASS" if all(r.verdict == "pass" for r in results) else "FAIL"
    total_cases = sum(r.total for r in results)
    total_passed = sum(r.passed for r in results)
    lines.append(
        f"Overall: **{overall}** — {total_passed}/{total_cases} cases across "
        f"{len(results)} evals."
    )
    lines.append("")
    lines.append("| Eval | Verdict | Pass rate | Threshold | Cases | Seconds |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.eval_name} | **{r.verdict}** | "
            f"{r.passed}/{r.total} ({r.rate * 100:.0f}%) | "
            f"{r.threshold * 100:.0f}% | {r.total} | {r.elapsed_seconds:.3f} |"
        )
    lines.append("")

    for r in results:
        lines.append(f"## {r.eval_name}")
        lines.append("")
        lines.append(f"Verdict: **{r.verdict}** ({r.passed}/{r.total} passed).")
        lines.append("")
        lines.append("| Case | Outcome | Expected | Actual | Note |")
        lines.append("|---|---|---|---|---|")
        for c in r.cases:
            mark = "OK" if c.passed else "FAIL"
            exp = _short(c.expected)
            act = _short(c.actual)
            note = c.note.replace("|", "\\|") if c.note else ""
            lines.append(f"| {c.name} | {mark} | `{exp}` | `{act}` | {note} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Reproducibility: every eval is deterministic. Inputs are inlined, the LLM is "
        "mocked via the router's `complete_fn`, and the harness writes no external state. "
        "Rerun with `midas eval` from a fresh checkout to verify."
    )
    return "\n".join(lines)


def _short(value: object, *, limit: int = 80) -> str:
    s = repr(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."
