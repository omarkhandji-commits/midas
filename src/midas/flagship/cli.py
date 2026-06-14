"""MIDAS command-line interface (Typer). Fleshed out in the channels milestone."""

from __future__ import annotations

import sys

import typer

# Force UTF-8 stdout so reports/diacritics render on Windows consoles (cp1252).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - best-effort console fix
        pass

app = typer.Typer(help="MIDAS - autonomous revenue operator.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """MIDAS — the autonomous revenue operator. Run a subcommand below."""


@app.command()
def version() -> None:
    """Print the MIDAS version."""
    from midas import __version__

    typer.echo(f"MIDAS {__version__}")


@app.command()
def eval(
    out: str | None = typer.Option(
        None, "--out", "-o", help="Write the Transparency Report to this path (markdown).",
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run the Proof-First eval suite and print/save a Transparency Report.

    Deterministic, offline, vendor-neutral. Anyone can rerun this and reproduce the
    same numbers from a fresh checkout.
    """
    from pathlib import Path

    from midas.core.eval import render_report
    from midas.flagship.eval import build_suite

    policy_path = Path(base_dir) / "config" / "policy.yml"
    results = build_suite(policy_path).run()
    report = render_report(results)

    if out:
        Path(out).write_text(report, encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(report)

    # Non-zero exit on failure so CI can gate on the suite.
    failed = [r for r in results if r.verdict != "pass"]
    if failed:
        raise typer.Exit(code=1)


@app.command()
def scan(
    niche: str = typer.Argument(..., help="The niche to scan, e.g. 'tools for plumbers'."),
    live: bool = typer.Option(
        False, "--live", help="Use real LLM calls (needs API keys in .env) instead of demo data."
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/ and .env."),
) -> None:
    """Scan a niche and print a proven, prepared Daily Revenue Move.

    Without --live, runs offline on bundled demo data (no API key needed). The move
    always stops before any outbound action — you approve and execute it.
    """
    from midas.flagship.flows.render import render_report

    if live:
        from midas.flagship.flows import scan_niche
        from midas.flagship.runtime import build_runtime

        rt = build_runtime(base_dir)
        report = scan_niche(niche, router=rt.router, ledger=rt.ledger, task_id="scan")
    else:
        from midas.flagship.flows import run_scan
        from midas.flagship.flows.demo import demo_candidates

        report = run_scan(niche, demo_candidates())

    typer.echo(render_report(report))


if __name__ == "__main__":
    app()
