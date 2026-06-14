"""MIDAS command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from midas.core.receipts.models import Decision

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - best-effort console fix
        pass

app = typer.Typer(help="MIDAS - autonomous revenue operator.", no_args_is_help=True)
approvals_app = typer.Typer(help="Review approval-gated actions.", no_args_is_help=True)
memory_app = typer.Typer(help="Store and search business memory.", no_args_is_help=True)
competitors_app = typer.Typer(
    help="Track competitor pages and market changes.", no_args_is_help=True
)
assets_app = typer.Typer(help="Generate business assets.", no_args_is_help=True)
outcome_app = typer.Typer(help="Record what happened after a move.", no_args_is_help=True)

app.add_typer(approvals_app, name="approvals")
app.add_typer(memory_app, name="memory")
app.add_typer(competitors_app, name="competitors")
app.add_typer(assets_app, name="assets")
app.add_typer(outcome_app, name="outcome")


@app.callback()
def _main() -> None:
    """MIDAS: proof-first business operator. Run a subcommand below."""


@app.command()
def version() -> None:
    """Print the MIDAS version."""
    from midas import __version__

    typer.echo(f"MIDAS {__version__}")


@app.command()
def setup(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Initialize local state, signing key, memory, cache, approvals, and ledger."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    rt.append_receipt(
        run_id="setup",
        agent="cli",
        tool="setup",
        inputs={"base_dir": str(rt.base_dir)},
        outputs={"state_dir": str(rt.ledger.path.parent)},
    )
    typer.echo(f"MIDAS state ready: {rt.ledger.path.parent}")
    typer.echo("Local-first defaults active: approval-gated outbound actions, receipts, memory.")


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Loopback host only."),
    port: int = typer.Option(8765, "--port", help="Local dashboard port."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Start the local Midas Operator Console."""
    from midas.flagship.dashboard import create_app
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    deps = rt.dashboard_deps(allowed_host=f"{host}:{port}")
    typer.echo(f"Dashboard login token: {deps.login_token.value}")
    typer.echo(f"Opening local console at http://{host}:{port}")
    import uvicorn

    uvicorn.run(create_app(deps, bind_host=host), host=host, port=port, log_level="warning")


@app.command()
def eval(
    out: str | None = typer.Option(
        None, "--out", "-o", help="Write the Transparency Report to this path."
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run the deterministic Proof-First eval suite."""
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
    if [r for r in results if r.verdict != "pass"]:
        raise typer.Exit(code=1)


@app.command()
def scan(
    niche: str = typer.Argument(..., help="The niche to scan, e.g. 'tools for plumbers'."),
    live: bool = typer.Option(False, "--live", help="Use real LLM/search plumbing."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Produce a Daily Revenue Move and queue approval for the next outbound action."""
    from midas.flagship.flows import run_scan, scan_niche
    from midas.flagship.flows.demo import demo_candidates
    from midas.flagship.flows.render import render_report
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    run_id = f"scan:{niche}"
    if live:
        report = scan_niche(
            niche,
            router=rt.router,
            search=rt.search,
            verifier=rt.verifier,
            ledger=rt.ledger,
            memory=rt.memory,
            run_id=run_id,
            task_id=run_id,
        )
    else:
        report = run_scan(niche, demo_candidates(), ledger=rt.ledger, memory=rt.memory)
    approval_id = _queue_move_approval(rt, report, run_id=run_id)
    rt.append_receipt(
        run_id=run_id,
        agent="cli",
        tool="scan",
        inputs={"niche": niche, "live": live},
        outputs={
            "daily_move": bool(report.daily_move),
            "proof_level": report.proof_level.value,
            "approval_id": approval_id,
        },
    )
    typer.echo(render_report(report))
    if approval_id is not None:
        typer.echo(f"Approval queued: #{approval_id}")


@approvals_app.command("list")
def approvals_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List pending approvals."""
    from midas.flagship.runtime import build_runtime

    pending = build_runtime(base_dir).approvals.pending()
    if not pending:
        typer.echo("No pending approvals.")
        return
    for req in pending:
        typer.echo(f"#{req.id} [{req.action}] {req.summary} ({req.tool}/{req.agent})")


@approvals_app.command("approve")
def approvals_approve(
    request_id: int = typer.Argument(..., help="Approval id."),
    note: str | None = typer.Option(None, "--note"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Approve a queued action."""
    from midas.flagship.runtime import build_runtime

    req = build_runtime(base_dir).approvals.approve(request_id, by="cli", note=note)
    typer.echo(f"Approved #{req.id}: {req.summary}")


@approvals_app.command("reject")
def approvals_reject(
    request_id: int = typer.Argument(..., help="Approval id."),
    note: str | None = typer.Option(None, "--note"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Reject a queued action."""
    from midas.flagship.runtime import build_runtime

    req = build_runtime(base_dir).approvals.reject(request_id, by="cli", note=note)
    typer.echo(f"Rejected #{req.id}: {req.summary}")


@memory_app.command("add")
def memory_add(
    kind: Annotated[str, typer.Argument(help="user/business/decision/result/market/error")],
    key: str = typer.Argument(...),
    content: str = typer.Argument(...),
    source: Annotated[list[str] | None, typer.Option("--source", "-s")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", "-t")] = None,
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Add or supersede a memory entry."""
    from midas.core.agents.summary import ProofLevel
    from midas.core.memory import MemoryKind
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    entry = rt.memory.remember(
        MemoryKind(kind),
        key,
        content,
        proof_level=ProofLevel.MEDIUM if source else ProofLevel.LOW,
        sources=source or [],
        tags=tag or [],
    )
    rt.append_receipt(
        run_id="memory:add",
        agent="cli",
        tool="memory.add",
        inputs={"kind": kind, "key": key},
        outputs={"id": entry.id, "proof_level": entry.proof_level.value},
    )
    typer.echo(f"Remembered #{entry.id} [{entry.kind.value}] {entry.key}")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument("", help="Keyword query."),
    kind: str | None = typer.Option(None, "--kind"),
    limit: int = typer.Option(10, "--limit"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Search live memory."""
    from midas.core.memory import MemoryKind
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    rows = rt.memory.recall(
        kind=MemoryKind(kind) if kind else None,
        query=query or None,
        limit=limit,
    )
    for row in rows:
        typer.echo(
            f"#{row.id} [{row.kind.value}/{row.proof_level.value}] "
            f"{row.key}: {row.content}"
        )


@memory_app.command("export")
def memory_export(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Export live memory as JSON."""
    from midas.flagship.runtime import build_runtime

    rows = build_runtime(base_dir).memory.recall(limit=10_000)
    typer.echo(json.dumps([_memory_json(r) for r in rows], indent=2, ensure_ascii=False))


@competitors_app.command("add")
def competitors_add(
    name: str = typer.Argument(...),
    url: str = typer.Argument(...),
    notes: str = typer.Option("", "--notes"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Track a competitor URL."""
    from midas.core.memory import MemoryKind
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    comp = rt.competitors.add(name, url, notes=notes)
    rt.memory.remember(
        MemoryKind.MARKET,
        f"competitor:{comp.id}",
        f"Tracking competitor {comp.name} at {comp.url}. {notes}",
        sources=[comp.url],
        tags=["competitor"],
    )
    rt.append_receipt(
        run_id="competitors:add",
        agent="cli",
        tool="competitors.add",
        inputs={"name": name, "url": url},
        outputs={"id": comp.id},
    )
    typer.echo(f"Tracking competitor #{comp.id}: {comp.name} -> {comp.url}")


@competitors_app.command("list")
def competitors_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List tracked competitors."""
    from midas.flagship.runtime import build_runtime

    rows = build_runtime(base_dir).competitors.list()
    if not rows:
        typer.echo("No competitors tracked.")
        return
    for comp in rows:
        typer.echo(f"#{comp.id} {comp.name} -> {comp.url}")


@competitors_app.command("watch")
def competitors_watch(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Fetch competitor pages and record dated snapshots/diffs."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    snaps = rt.competitors.watch_all(fetcher=rt.fetcher, memory=rt.memory, ledger=rt.ledger)
    if not snaps:
        typer.echo("No competitors tracked.")
        return
    for snap in snaps:
        typer.echo(
            f"{snap.name}: {snap.change_kind} status={snap.status} "
            f"hash={snap.content_hash[:12]}"
        )


@assets_app.command("generate")
def assets_generate(
    topic: str = typer.Argument(..., help="Offer/opportunity name."),
    summary: str = typer.Option("", "--summary"),
    output_dir: str | None = typer.Option(None, "--output-dir", "-o"),
    live: bool = typer.Option(False, "--live", help="Use configured LLM router."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Generate approval-gated business assets."""
    from midas.flagship.assets import heuristic_assets, llm_assets, write_asset_files
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    candidate = _candidate_from_topic(topic, summary or f"Draft business move for {topic}.")
    assets = llm_assets(candidate, router=rt.router) if live else heuristic_assets(candidate)
    if output_dir:
        written = write_asset_files(assets, output_dir)
        rt.append_receipt(
            run_id="assets:generate",
            agent="cli",
            tool="assets.generate",
            inputs={"topic": topic, "output_dir": output_dir, "live": live},
            outputs={"files": {k: str(v) for k, v in written.items()}},
        )
        for key, path in written.items():
            typer.echo(f"{key}: {path}")
        return
    typer.echo(json.dumps(assets.as_dict(), indent=2, ensure_ascii=False))


@outcome_app.command("record")
def outcome_record(
    move_key: str = typer.Argument(...),
    outcome: str = typer.Argument(...),
    metric: Annotated[
        list[str] | None,
        typer.Option("--metric", "-m", help="key=value"),
    ] = None,
    source: Annotated[list[str] | None, typer.Option("--source", "-s")] = None,
    note: str = typer.Option("", "--note"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Record replies, sales, clicks, failures, or other observed outcomes."""
    from midas.flagship.outcomes import Outcome, ingest_outcome
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    entry = ingest_outcome(
        Outcome(
            move_key=move_key,
            outcome=outcome,
            metrics=_parse_metrics(metric or []),
            sources=source or [],
            note=note,
        ),
        memory=rt.memory,
        ledger=rt.ledger,
        run_id="outcome:record",
    )
    typer.echo(f"Outcome recorded #{entry.id} proof={entry.proof_level.value}")


@app.command()
def export(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Export a compact local audit bundle as JSON."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    body = {
        "memory": [_memory_json(r) for r in rt.memory.recall(limit=10_000)],
        "competitors": [c.__dict__ for c in rt.competitors.list()],
        "approvals_pending": [a.__dict__ for a in rt.approvals.pending()],
        "receipts": [r.model_dump(mode="json") for r in rt.ledger],
        "cache_stats": rt.research_cache.stats(),
    }
    typer.echo(json.dumps(body, indent=2, ensure_ascii=False, default=str))


def _queue_move_approval(rt: object, report: object, *, run_id: str) -> int | None:
    move = getattr(report, "daily_move", None)
    if move is None:
        return None
    req = rt.approvals.enqueue(  # type: ignore[attr-defined]
        run_id=run_id,
        agent="midas",
        tool="business_asset",
        action="external_send",
        summary=f"Approve next action for {move.candidate.name}: {move.next_action}",
        payload={
            "candidate": move.candidate.name,
            "next_action": move.next_action,
            "asset_keys": sorted(move.brief.draft_assets),
        },
    )
    rt.append_receipt(  # type: ignore[attr-defined]
        run_id=run_id,
        agent="cli",
        tool="approval.enqueue",
        decision=Decision.QUEUE_APPROVAL,
        inputs={"candidate": move.candidate.name},
        outputs={"approval_id": req.id},
    )
    return req.id


def _candidate_from_topic(topic: str, summary: str):
    from midas.core.agents.summary import Finding, ProofLevel
    from midas.flagship.opportunity import OpportunityCandidate
    from midas.flagship.scoring import FactorScores

    return OpportunityCandidate(
        name=topic,
        summary=summary,
        findings=[Finding(f"Operator-supplied asset request for {topic}.", ProofLevel.LOW)],
        factors=FactorScores(**{k: 7 for k in FactorScores.model_fields}),
    )


def _parse_metrics(items: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise typer.BadParameter(f"metric must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = float(value)
    return out


def _memory_json(row: Any) -> dict[str, object]:
    return {
        "id": row.id,
        "ts": row.ts,
        "kind": row.kind.value,
        "key": row.key,
        "content": row.content,
        "proof_level": row.proof_level.value,
        "sources": row.sources,
        "tags": row.tags,
        "superseded": row.superseded,
    }


if __name__ == "__main__":
    app()
