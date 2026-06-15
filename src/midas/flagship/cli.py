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
providers_app = typer.Typer(help="Configure and diagnose LLM providers.", no_args_is_help=True)
schedule_app = typer.Typer(
    help="Create user-installed cron/scheduler recipes.", no_args_is_help=True
)
skills_app = typer.Typer(
    help="Create and install approval-gated MIDAS skills.", no_args_is_help=True
)
media_app = typer.Typer(
    help="Inspect local PDFs, images, audio, and video safely.", no_args_is_help=True
)
voice_app = typer.Typer(
    help="Draft voice messages and approval-gated call plans.", no_args_is_help=True
)
keys_app = typer.Typer(
    help="Inspect public signing keys (Receipt v1).", no_args_is_help=True
)

app.add_typer(approvals_app, name="approvals")
app.add_typer(memory_app, name="memory")
app.add_typer(competitors_app, name="competitors")
app.add_typer(assets_app, name="assets")
app.add_typer(outcome_app, name="outcome")
app.add_typer(providers_app, name="providers")
app.add_typer(schedule_app, name="schedule")
app.add_typer(skills_app, name="skills")
app.add_typer(media_app, name="media")
app.add_typer(voice_app, name="voice")
app.add_typer(keys_app, name="keys")


@keys_app.command("export-public")
def keys_export_public(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Print the Ed25519 public key used to sign this install's Receipt v1 ledger.

    Hand this hex string to anyone who wants to verify your receipts independently
    with ``python -m midas_verify <ledger.jsonl> --public-key <hex>``.
    """
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    typer.echo(rt.ledger.public_key_hex)


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
def up(
    host: str = typer.Option("127.0.0.1", "--host", help="Loopback host only."),
    port: int = typer.Option(8765, "--port", help="Local dashboard port."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Start dashboard and configured listeners together."""
    import asyncio

    import uvicorn

    from midas.flagship.channel_settings import TelegramLongPollListener
    from midas.flagship.dashboard import create_app
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    deps = rt.dashboard_deps(allowed_host=f"{host}:{port}")
    typer.echo(f"Dashboard login token: {deps.login_token.value}")
    typer.echo(f"Starting local console at http://{host}:{port}")
    telegram_config = rt.channels.telegram_config()
    if telegram_config is None:
        typer.echo("Telegram listener: not configured")
    else:
        typer.echo("Telegram listener: configured")

    async def _serve() -> None:
        tasks = []
        if telegram_config is not None:
            listener = TelegramLongPollListener(config=telegram_config, queue=rt.approvals)
            tasks.append(asyncio.create_task(listener.run_forever()))
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(deps, bind_host=host),
                host=host,
                port=port,
                log_level="warning",
            )
        )
        tasks.append(asyncio.create_task(server.serve()))
        await asyncio.gather(*tasks)

    asyncio.run(_serve())


@app.command()
def eval(
    out: str | None = typer.Option(
        None, "--out", "-o", help="Write the Transparency Report to this path."
    ),
    suite: str = typer.Option(
        "all",
        "--suite",
        help="Eval subset: 'all' (default) or 'tau' for τ-bench-only rule adherence.",
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run the deterministic Proof-First eval suite."""
    from midas.core.eval import render_report
    from midas.flagship.eval import build_suite

    policy_path = Path(base_dir) / "config" / "policy.yml"
    full = build_suite(policy_path)
    if suite == "tau":
        chosen = [e for e in full.evals if "τ-bench" in e.name or "tau" in e.name.lower()]
        if not chosen:
            raise typer.BadParameter("no τ-bench eval registered in the suite")
        from midas.core.eval import Suite

        results = Suite(name=f"{full.name} — τ-bench only", evals=chosen).run()
    elif suite == "all":
        results = full.run()
    else:
        raise typer.BadParameter("--suite must be 'all' or 'tau'")
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
    mode: str = typer.Option("deep", "--mode", help="fast/deep/war-room."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Produce a Daily Revenue Move and queue approval for the next outbound action."""
    from midas.flagship.flows import run_scan, scan_niche
    from midas.flagship.flows.demo import demo_candidates
    from midas.flagship.flows.render import render_report
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    if mode not in {"fast", "deep", "war-room"}:
        raise typer.BadParameter("mode must be fast, deep, or war-room")
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
            "mode": mode,
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


@providers_app.command("list")
def providers_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List known providers and local/key status without calling the network."""
    from midas.core.providers import diagnose_providers
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    for status in diagnose_providers(rt.config.providers):
        state = "ready" if status.configured else "missing"
        local = " local" if status.local else ""
        missing = f" missing={','.join(status.missing)}" if status.missing else ""
        typer.echo(f"{status.name}: {state}{local}{missing}")


@providers_app.command("doctor")
def providers_doctor(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Explain routing roles, council setup, and missing provider env vars."""
    from midas.core.providers import diagnose_providers
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    cfg = rt.config.providers
    typer.echo("Roles:")
    for role, rc in cfg.roles.items():
        fallbacks = f" -> {', '.join(rc.fallbacks)}" if rc.fallbacks else ""
        typer.echo(f"- {role}: {rc.primary}{fallbacks}")
    typer.echo("Council:")
    typer.echo(
        f"- enabled={cfg.council.enabled} members={len(cfg.council.members)} "
        f"chairman={cfg.council.chairman or 'unset'}"
    )
    typer.echo("Providers:")
    for status in diagnose_providers(cfg):
        if status.configured:
            typer.echo(f"- OK {status.name}")
        else:
            typer.echo(f"- MISSING {status.name}: {', '.join(status.missing) or 'not configured'}")


@providers_app.command("example")
def providers_example(provider: str = typer.Argument(..., help="Provider name.")) -> None:
    """Print a safe providers.yml snippet for one provider."""
    from midas.core.providers import render_provider_example

    typer.echo(render_provider_example(provider))


@providers_app.command("add")
def providers_add(
    provider: str = typer.Argument(..., help="Provider key, e.g. ollama/openrouter/openai."),
    role: str | None = typer.Option(None, "--role", help="Role to set/update, e.g. cheap."),
    model: str | None = typer.Option(None, "--model", help="LiteLLM model id for the role."),
    fallback: Annotated[list[str] | None, typer.Option("--fallback")] = None,
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Add provider metadata and optionally wire a model role. Secrets stay in env vars."""
    from midas.core.providers import catalog, render_provider_example

    path = _providers_config_path(base_dir)
    data = _read_providers_yaml(path)
    data.setdefault("providers", {})
    if provider not in data["providers"]:
        snippet = render_provider_example(provider)
        import yaml

        snippet_data = yaml.safe_load(snippet) or {}
        data["providers"].update(snippet_data)
    if role and model:
        data.setdefault("roles", {})
        data["roles"][role] = {"primary": model, "fallbacks": fallback or []}
    elif role or model:
        raise typer.BadParameter("--role and --model must be used together")
    _write_providers_yaml(path, data)
    known = provider in catalog()
    typer.echo(f"Provider {provider} {'configured' if known else 'added as custom'} in {path}")
    if role and model:
        typer.echo(f"Role {role}: {model}")


@providers_app.command("test")
def providers_test(
    model: str = typer.Argument(..., help="Model id to test, e.g. ollama/llama3.1."),
    live: bool = typer.Option(False, "--live", help="Make a real provider call."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Dry-run or live-test a single model through the MIDAS router."""
    from midas.core.router import ChatResult, LLMRouter
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    if live:
        res = rt.router.complete_model(
            model,
            [{"role": "user", "content": "Reply with MIDAS_OK only."}],
            task_id=f"provider:test:{model}",
            run_id="provider:test",
            est_usd=0.02,
        )
    else:
        router = LLMRouter(
            rt.config.providers,
            complete_fn=lambda m, msgs: ChatResult(
                text="MIDAS_OK", model=m, prompt_tokens=6, completion_tokens=3, cost_usd=0.0
            ),
        )
        res = router.complete_model(model, [{"role": "user", "content": "dry"}])
    typer.echo(f"{res.model}: {res.text.strip()} cost=${res.cost_usd or 0:.6f}")


@app.command()
def do(
    task: str = typer.Argument(..., help="What you want MIDAS to do in the workspace."),
    max_steps: int = typer.Option(6, "--max-steps", help="Loop iteration cap."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run the gated agent loop on a task. Mutations queue approvals; reads run inline."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    loop = rt.agent_loop(run_id=f"do:{task[:32]}", max_steps=max_steps)
    transcript = loop.run(task)
    typer.echo(json.dumps(transcript.to_json(), indent=2, ensure_ascii=False))
    if transcript.queued_approvals:
        typer.echo(
            f"\n{len(transcript.queued_approvals)} approval(s) queued: "
            f"{transcript.queued_approvals}. Resolve with `midas approvals approve <id>`."
        )

    # Post-run: ask AutoSkills to detect proposals from the receipts this run produced.
    # Surfaces sequences worth reusing without ever running anything automatically.
    proposals = _autoskills(rt).detect()
    if proposals:
        typer.echo(
            "\nAuto-skill proposals from this run "
            "(review with `midas skills auto-list`):"
        )
        for p in proposals:
            scope = "local" if p.local_only else "needs-approval"
            typer.echo(f"  - {p.proposal_id}  [{scope}]  {p.name}")


@app.command()
def fill(
    target: str = typer.Argument(..., help="Spreadsheet to fill (.xlsx or .csv)."),
    sources: Annotated[
        list[str] | None,
        typer.Option("--from", "-f", help="PDFs (or text files) to extract rows from."),
    ] = None,
    sheet_name: str = typer.Option("Sheet1", "--sheet", help="Sheet name (xlsx only)."),
    start_row: int = typer.Option(1, "--start-row", help="First spreadsheet row to write."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Extract rows from one or more PDFs and queue a sheet.write approval.

    The PDF→cells mapping is DETERMINISTIC (no LLM) — the operator approves real
    cells with real values. Use ``midas execute <approval_id>`` to materialize the
    write after review.
    """
    from midas.flagship.agent.tools.data import extract_rows, rows_to_cells
    from midas.flagship.agent.tools.pdf import pdf_extract
    from midas.flagship.agent.tools.sheet import plan_sheet_write
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    if rt.fs_guard is None:
        raise typer.BadParameter("fs_guard not initialized — run `midas setup` first")
    rows = []
    for src in sources or []:
        extracted = pdf_extract(rt.fs_guard, src)
        rows.extend(extract_rows(extracted.text))
    if not rows:
        raise typer.BadParameter(
            "no recognizable rows in the sources (label:value or date amount)"
        )
    cells = rows_to_cells(rows, start_row=start_row)
    plan = plan_sheet_write(rt.fs_guard, target, sheet_name=sheet_name, cells=cells)
    req = rt.approvals.enqueue(
        run_id=f"fill:{target}",
        agent="cli",
        tool="sheet.write",
        action="write_spreadsheet",
        summary=f"Fill {plan.cell_count} cells in {plan.path} (range {plan.cell_range})",
        payload={
            "path": plan.path,
            "sheet_name": plan.sheet_name,
            "cells": plan.cells,
            "sha256_prev": plan.sha256_prev,
        },
    )
    rt.append_receipt(
        run_id=f"fill:{target}",
        agent="cli",
        tool="sheet.write",
        decision=Decision.QUEUE_APPROVAL,
        inputs={"target": target, "sources": sources, "rows": len(rows)},
        outputs={"approval_id": req.id, "cells": plan.cell_count, "range": plan.cell_range},
    )
    typer.echo(
        json.dumps(
            {
                "approval_id": req.id,
                "path": plan.path,
                "cells": plan.cell_count,
                "range": plan.cell_range,
                "next": f"midas execute {req.id}",
            },
            indent=2,
        )
    )


@app.command()
def execute(
    approval_id: int = typer.Argument(..., help="An approved request id."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Execute a previously-approved gated step (fs.write / code.run / sheet.write).

    Reads the approval from the queue, confirms it is APPROVED, runs the underlying
    executor, and writes a receipt naming the concrete outcome (sha256 / cell range /
    subprocess exit code).
    """
    from midas.core.approvals.queue import ApprovalStatus
    from midas.flagship.agent.execute import execute_approved_step
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    request = rt.approvals.get(approval_id)
    if request is None:
        raise typer.BadParameter(f"unknown approval id: {approval_id}")
    if request.status != ApprovalStatus.APPROVED:
        raise typer.BadParameter(
            f"approval #{approval_id} is {request.status.value} — must be approved first"
        )
    result = execute_approved_step(rt, request)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command()
def research(
    question: str = typer.Argument(..., help="The question to research."),
    k: int = typer.Option(5, "--k", help="Max sources to consider."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run a débrouillard web research pass and print a cited synthesis.

    Searches, fetches, and verifies live sources before answering. A claim with zero
    reachable sources is reported as LOW proof level — never HIGH-without-verification.
    """
    from midas.core.web import research as run_research
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    result = run_research(
        question,
        search=rt.search,
        fetcher=rt.fetcher,
        verifier=rt.verifier,
        k=k,
    )
    rt.append_receipt(
        run_id="research",
        agent="cli",
        tool="research.run",
        inputs={"question": question, "k": k},
        outputs={
            "verified": result.verified_count,
            "proof_level": result.proof_level.value,
            "sources": [s.url for s in result.sources],
        },
    )
    typer.echo(result.synthesis)
    typer.echo(f"\nproof_level: {result.proof_level.value}")
    typer.echo(f"verified_sources: {result.verified_count}/{len(result.sources)}")


@app.command()
def council(
    question: str = typer.Argument(..., help="High-stakes question to debate."),
    live: bool = typer.Option(False, "--live", help="Use real configured models."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run a budgeted multi-LLM council for high-stakes decisions."""
    from midas.core.router import ChatResult, Council, LLMRouter
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    cfg = rt.config.providers.council
    members = cfg.members or [rc.primary for rc in rt.config.providers.roles.values()]
    chairman = cfg.chairman or (members[0] if members else "local/mock")
    messages = [
        {
            "role": "system",
            "content": (
                "You are one member of a proof-first business council. "
                "State assumptions, risks, evidence needed, and a clear recommendation."
            ),
        },
        {"role": "user", "content": question},
    ]
    router = rt.router if live else LLMRouter(
        rt.config.providers,
        complete_fn=lambda m, msgs: ChatResult(
            text=f"{m}: recommendation requires evidence, approval, and outcome tracking.",
            model=m,
            prompt_tokens=50,
            completion_tokens=20,
            cost_usd=0.0,
        ),
    )
    result = Council(
        router,
        members=members,
        chairman=chairman,
        agreement_threshold=cfg.agreement_threshold,
    ).deliberate(messages, run_id="council", task_id="council", est_usd_each=0.02)
    typer.echo(f"Agreement: {result.agreement:.2f}")
    typer.echo(f"Human approval needed: {result.escalate_to_human}")
    typer.echo(result.final.text)


@schedule_app.command("add")
def schedule_add(
    name: str = typer.Argument(..., help="Local recipe name."),
    niche: str = typer.Argument(..., help="Business/niche to scan."),
    at: str = typer.Option("09:00", "--at", help="HH:MM local time."),
    mode: str = typer.Option("deep", "--mode", help="fast/deep/war-room."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Store and print a user-installed daily scan schedule recipe."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.schedule import ScheduleStore, daily_scan_recipe

    if mode not in {"fast", "deep", "war-room"}:
        raise typer.BadParameter("mode must be fast, deep, or war-room")
    rt = build_runtime(base_dir)
    recipe = daily_scan_recipe(
        name=name,
        niche=niche,
        at=at,
        base_dir=str(rt.base_dir),
        mode=mode,
    )
    ScheduleStore(rt.state_dir / "schedules.json").add(recipe)
    rt.append_receipt(
        run_id="schedule:add",
        agent="cli",
        tool="schedule.add",
        inputs={"name": name, "niche": niche, "at": at, "mode": mode},
        outputs={"command": recipe.command},
    )
    _print_schedule_recipe(recipe)


@schedule_app.command("list")
def schedule_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List stored schedule recipes."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.schedule import ScheduleStore

    rt = build_runtime(base_dir)
    rows = ScheduleStore(rt.state_dir / "schedules.json").list()
    if not rows:
        typer.echo("No schedule recipes.")
        return
    for row in rows:
        typer.echo(f"{row.name}: {row.cadence} at {row.at} -> {row.command}")


@schedule_app.command("recipe")
def schedule_recipe(
    niche: str = typer.Argument(..., help="Business/niche to scan."),
    at: str = typer.Option("09:00", "--at", help="HH:MM local time."),
    mode: str = typer.Option("deep", "--mode", help="fast/deep/war-room."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Print schedule commands without storing anything."""
    from midas.flagship.schedule import daily_scan_recipe

    if mode not in {"fast", "deep", "war-room"}:
        raise typer.BadParameter("mode must be fast, deep, or war-room")
    _print_schedule_recipe(
        daily_scan_recipe(name="daily-scan", niche=niche, at=at, base_dir=base_dir, mode=mode)
    )


@skills_app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name."),
    summary: str = typer.Argument(..., help="What the skill helps MIDAS do."),
    permission: Annotated[list[str] | None, typer.Option("--permission", "-p")] = None,
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Create a local MIDAS skill template."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.skills import SkillRegistry

    rt = build_runtime(base_dir)
    manifest = SkillRegistry(rt.state_dir).create(
        name=name,
        summary=summary,
        permissions=permission or ["read"],
    )
    rt.append_receipt(
        run_id="skills:create",
        agent="cli",
        tool="skills.create",
        inputs={"name": name, "permissions": permission or ["read"]},
        outputs={"skill": manifest.name, "sha256": manifest.sha256},
    )
    typer.echo(f"Created skill {manifest.name} sha256={manifest.sha256[:16]}")


@skills_app.command("list")
def skills_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List installed local skills."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.skills import SkillRegistry

    rt = build_runtime(base_dir)
    rows = SkillRegistry(rt.state_dir).list()
    if not rows:
        typer.echo("No local MIDAS skills installed.")
        return
    for row in rows:
        perms = ",".join(row.permissions)
        typer.echo(f"{row.name} {row.version} perms={perms} sha={row.sha256[:12]}")


@skills_app.command("install")
def skills_install(
    source: str = typer.Argument(..., help="Local skill folder. Remote URLs use plan-download."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Install a local skill folder after static safety validation."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.skills import SkillRegistry, is_remote_skill_source

    if is_remote_skill_source(source):
        raise typer.BadParameter("remote skill sources require `midas skills plan-download`")
    rt = build_runtime(base_dir)
    try:
        manifest = SkillRegistry(rt.state_dir).install_local(source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    rt.append_receipt(
        run_id="skills:install",
        agent="cli",
        tool="skills.install",
        inputs={"source": source},
        outputs={"skill": manifest.name, "sha256": manifest.sha256},
    )
    typer.echo(f"Installed skill {manifest.name} sha256={manifest.sha256[:16]}")


@skills_app.command("plan-download")
def skills_plan_download(
    url: str = typer.Argument(..., help="Remote Git/HTTPS skill source."),
    reason: str = typer.Option("", "--reason", help="Why this skill is needed."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Queue approval for a remote skill download; does not download or execute."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.skills import is_remote_skill_source

    if not is_remote_skill_source(url):
        raise typer.BadParameter("plan-download expects a remote URL")
    rt = build_runtime(base_dir)
    req = rt.approvals.enqueue(
        run_id="skills:plan-download",
        agent="midas",
        tool="skills.download",
        action="external_fetch",
        summary=f"Review remote skill before download: {url}",
        payload={"url": url, "reason": reason, "requires_manual_review": True},
    )
    rt.append_receipt(
        run_id="skills:plan-download",
        agent="cli",
        tool="skills.plan_download",
        decision=Decision.QUEUE_APPROVAL,
        inputs={"url": url},
        outputs={"approval_id": req.id},
    )
    typer.echo(f"Approval queued for remote skill review: #{req.id}")


def _autoskills(rt: Any) -> Any:
    from midas.flagship.autoskills import AutoSkills, AutoSkillsStore

    store = AutoSkillsStore(rt.state_dir / "autoskills.json")
    return AutoSkills(
        registry=rt.skill_registry,
        ledger=rt.ledger,
        queue=rt.approvals,
        store=store,
        search=rt.search,
    )


@skills_app.command("auto-list")
def skills_auto_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Detect and list pending auto-skill proposals from the receipt ledger."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    auto = _autoskills(rt)
    auto.detect()
    pending = auto._store.pending()  # noqa: SLF001 - private store access intentional
    if not pending:
        typer.echo("No pending auto-skill proposals.")
        return
    for p in pending:
        scope = "local" if p.local_only else "needs-approval"
        typer.echo(f"{p.proposal_id}  [{scope}]  {p.name} — {p.summary}")


@skills_app.command("auto-accept")
def skills_auto_accept(
    proposal_id: str = typer.Argument(..., help="Proposal id from `auto-list`."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Accept a local auto-skill proposal and install it as a draft skill."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    try:
        manifest = _autoskills(rt).accept(proposal_id)
    except (KeyError, ValueError, PermissionError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Accepted: {manifest.name} (sha256={manifest.sha256[:16]})")


@skills_app.command("auto-discard")
def skills_auto_discard(
    proposal_id: str = typer.Argument(..., help="Proposal id from `auto-list`."),
    reason: str = typer.Option("", "--reason", help="Why discard."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Discard a pending auto-skill proposal."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    try:
        _autoskills(rt).discard(proposal_id, reason=reason)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Discarded {proposal_id}.")


@media_app.command("inspect")
def media_inspect(
    path: str = typer.Argument(..., help="Local file to inspect."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Inspect a local document/media file without external model calls."""
    from midas.flagship.multimodal import inspect_media
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    inspection = inspect_media(path)
    rt.append_receipt(
        run_id="media:inspect",
        agent="cli",
        tool="media.inspect",
        inputs={"path": inspection.path},
        outputs={
            "kind": inspection.kind,
            "size_bytes": inspection.size_bytes,
            "sha256": inspection.sha256,
            "text_len": len(inspection.text),
            "warnings": inspection.warnings,
        },
    )
    typer.echo(json.dumps(inspection.as_dict(), indent=2, ensure_ascii=False))


@voice_app.command("draft")
def voice_draft(
    text: str = typer.Argument(..., help="Message to turn into a voice draft."),
) -> None:
    """Draft a voice note payload; sending still requires approval."""
    from midas.flagship.voice import draft_voice_message

    typer.echo(json.dumps(draft_voice_message(text).as_dict(), indent=2, ensure_ascii=False))


@voice_app.command("call-plan")
def voice_call_plan(
    contact: str = typer.Argument(..., help="Contact label, not scraped PII."),
    purpose: str = typer.Argument(..., help="Reason for the call."),
    offer: str = typer.Option("", "--offer", help="Offer/problem to discuss."),
    queue: bool = typer.Option(False, "--queue", help="Queue approval for this call plan."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Prepare a consent-first phone call plan; no phone call is placed."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.voice import plan_call

    plan = plan_call(contact_label=contact, purpose=purpose, offer=offer or purpose)
    if queue:
        rt = build_runtime(base_dir)
        req = rt.approvals.enqueue(
            run_id="voice:call-plan",
            agent="midas",
            tool="phone.call",
            action="phone_call",
            summary=f"Review call plan for {contact}: {purpose}",
            payload=plan.as_dict(),
        )
        rt.append_receipt(
            run_id="voice:call-plan",
            agent="cli",
            tool="voice.call_plan",
            decision=Decision.QUEUE_APPROVAL,
            inputs={"contact": contact, "purpose": purpose},
            outputs={"approval_id": req.id},
        )
    typer.echo(json.dumps(plan.as_dict(), indent=2, ensure_ascii=False))


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


def _providers_config_path(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    path = base / "config" / "providers.yml"
    if path.exists():
        return path
    return path


def _read_providers_yaml(path: Path) -> dict[str, Any]:
    import yaml

    if path.exists():
        return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    example = path.parent / "providers.example.yml"
    if example.exists():
        return dict(yaml.safe_load(example.read_text(encoding="utf-8")) or {})
    return {"roles": {}, "providers": {}, "routing": {}}


def _write_providers_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _print_schedule_recipe(recipe: Any) -> None:
    typer.echo(f"Command: {recipe.command}")
    typer.echo("\nWindows Task Scheduler:")
    typer.echo(recipe.windows_task)
    typer.echo("\ncron:")
    typer.echo(recipe.cron_line)
    typer.echo("\nGitHub Actions snippet:")
    typer.echo(recipe.github_actions)


if __name__ == "__main__":
    app()
