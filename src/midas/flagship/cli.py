"""MIDAS command-line interface."""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any

import typer

from midas.core.receipts.models import Decision

if hasattr(sys.stdout, "reconfigure"):
    with suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
capabilities_app = typer.Typer(
    help="Inspect local tools and plan safe fallbacks.", no_args_is_help=True
)
voice_app = typer.Typer(
    help="Draft voice messages and approval-gated call plans.", no_args_is_help=True
)
keys_app = typer.Typer(
    help="Inspect public signing keys (Receipt v1).", no_args_is_help=True
)
proof_app = typer.Typer(
    help="Export portable proof links (offline-verifiable HTML).", no_args_is_help=True
)
mcp_app = typer.Typer(
    help="MCP integration — serve MIDAS as an MCP server, or connect to external ones.",
    no_args_is_help=True,
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
app.add_typer(capabilities_app, name="capabilities")
app.add_typer(voice_app, name="voice")
app.add_typer(keys_app, name="keys")
app.add_typer(proof_app, name="proof")
app.add_typer(mcp_app, name="mcp")


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


@capabilities_app.command("scan")
def capabilities_scan(json_output: bool = typer.Option(False, "--json")) -> None:
    """Detect local free tools MIDAS can use. Never installs anything."""
    from midas.flagship.capabilities import scan_capabilities

    probes = scan_capabilities()
    if json_output:
        typer.echo(json.dumps({"capabilities": [p.as_dict() for p in probes]}, indent=2))
        return
    for probe in probes:
        marker = "ok" if probe.status == "available" else "setup"
        typer.echo(f"{marker:5} {probe.name:12} {probe.category:8} {probe.detail}")


@capabilities_app.command("plan")
def capabilities_plan(goal: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Explain the safest local/free path for a requested capability."""
    from midas.flagship.capabilities import plan_capability

    plan = plan_capability(goal)
    if json_output:
        typer.echo(json.dumps({"plan": plan.as_dict()}, indent=2))
        return
    typer.echo(f"Status: {plan.status}")
    typer.echo(f"Primary: {plan.primary_path}")
    typer.echo(f"Fallback: {plan.fallback_path}")
    typer.echo(f"Approval required: {plan.approval_required}")
    if plan.missing:
        typer.echo(f"Missing: {', '.join(plan.missing)}")


@app.command("repo-map")
def repo_map(
    subdir: str = typer.Argument(".", help="Workspace-relative directory to map."),
    top: int = typer.Option(20, "--top", help="Number of ranked files to show."),
    base_dir: str = typer.Option(".", "--base-dir", help="Workspace root."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Build the lightweight code map used by the native coder."""
    from midas.flagship.agent.tools.fsguard import FsGuard
    from midas.flagship.agent.tools.repo_map import build_repo_map

    guard = FsGuard(workspace=Path(base_dir).resolve())
    result = build_repo_map(guard, subdir=subdir)
    payload = {**result.as_dict(), "top": [f.to_dict() for f in result.top(n=top)]}
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(
        f"Repo map: {result.file_count} Python files, "
        f"{result.parse_errors} parse errors"
    )
    for entry in result.top(n=top):
        typer.echo(f"{entry.score:>4.0f}  {entry.path}")


@app.command("blog-lint")
def blog_lint(
    path: str = typer.Argument(..., help="Markdown file to lint."),
    title: str = typer.Option("", "--title", help="Optional page title."),
    meta_description: str = typer.Option("", "--meta", help="Optional meta description."),
    site_domain: str = typer.Option("", "--site", help="Domain for internal link checks."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run the deterministic SEO checklist on a Markdown post."""
    from midas.flagship.agent.tools.blog_seo import lint_blog

    markdown = Path(path).read_text(encoding="utf-8")
    result = lint_blog(
        markdown=markdown,
        title=title,
        meta_description=meta_description,
        site_domain=site_domain,
    )
    payload = result.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"SEO score: {result.score}/100")
    for issue in result.issues:
        typer.echo(f"{issue.severity:6} {issue.code}: {issue.message}")


@app.command("course")
def course(
    topic: str = typer.Argument(..., help="Course topic."),
    audience: str = typer.Option("beginners", "--audience", "-a", help="Target audience."),
    modules: int = typer.Option(5, "--modules", "-m", help="Number of modules."),
    objective: Annotated[
        list[str] | None,
        typer.Option("--objective", "-o", help="Learning objective; repeatable."),
    ] = None,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Draft a structured course outline."""
    from midas.flagship.agent.tools.course import plan_course_outline

    result = plan_course_outline(
        topic=topic,
        audience=audience,
        n_modules=modules,
        learning_objectives=objective or [],
    )
    if json_output:
        typer.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return
    typer.echo(result.markdown)


@app.command("drain")
def drain(
    now_iso: str | None = typer.Option(
        None,
        "--now",
        help="UTC ISO timestamp for deterministic draining; defaults to now.",
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Move due scheduled posts into the approval queue. Never auto-publishes."""
    from midas.flagship.agent.tools.social import plan_social_publish
    from midas.flagship.runtime import build_runtime
    from midas.flagship.scheduled_posts import drain_due

    rt = build_runtime(base_dir)

    def _plan(**kwargs: Any) -> Any:
        return plan_social_publish(rt.fs_guard, **kwargs)

    outcome = drain_due(
        rt.scheduled_posts,
        approvals=rt.approvals,
        plan_fn=_plan,
        run_id="cli:drain",
        now_iso=now_iso,
    )
    rt.append_receipt(
        run_id="cli:drain",
        agent="cli",
        tool="scheduled_posts.drain",
        inputs={"now_iso": now_iso},
        outputs=outcome.as_dict(),
    )
    payload = outcome.as_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(
        f"Queued {payload['enqueued_count']} due post(s); "
        f"failed {payload['failed_count']}."
    )


@app.command()
def init(
    key: str = typer.Option(
        "", "--key", help="LLM API key. Provider is detected from the prefix."
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
    no_test: bool = typer.Option(
        False, "--no-test", help="Skip the one-token smoke test."
    ),
    no_launch: bool = typer.Option(
        False,
        "--no-launch",
        help="Do not start the local dashboard or open the browser.",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Loopback host only."),
    port: int = typer.Option(8765, "--port", help="Local dashboard port."),
) -> None:
    """One command to a working setup: detect a local model or take an API key.

    Order of resolution:
    1. ``--key <APIKEY>`` — provider detected from prefix (OpenAI, Anthropic,
       OpenRouter, Groq, Google). Key written to ``.env``.
    2. A running local Ollama — an installed model is selected automatically.
    3. Neither — prints the two fastest paths to a working model.

    Then it initializes local state and runs a one-token smoke test so a green
    line means you can run `midas earn` immediately.
    """
    from midas.flagship.onboard import configure
    from midas.flagship.runtime import build_runtime

    base = Path(base_dir)
    result = configure(base, key=key or None)

    if result.mode == "none":
        typer.echo("No LLM configured yet. Two fast paths:\n")
        typer.echo("  Local, free, private (recommended):")
        typer.echo("    1. Install Ollama: https://ollama.com")
        typer.echo("    2. ollama pull llama3.1:8b")
        typer.echo("    3. midas init        # auto-detects it\n")
        typer.echo("  Cloud (one key):")
        typer.echo("    midas init --key sk-...           # OpenAI")
        typer.echo("    midas init --key sk-ant-...       # Anthropic")
        typer.echo("    midas init --key sk-or-...        # OpenRouter")
        if result.detail:
            typer.echo(f"\nNote: {result.detail}")
        raise typer.Exit(code=1)

    if result.mode == "local":
        typer.echo(f"Local model detected: {result.model} (no API key needed).")
    else:
        typer.echo(f"Configured {result.provider} → cheap role: {result.model}")

    # Initialize state (signing key, ledger, memory, approvals).
    rt = build_runtime(base_dir)
    rt.append_receipt(
        run_id="init",
        agent="cli",
        tool="init",
        inputs={"mode": result.mode, "provider": result.provider},
        outputs={"model": result.model},
    )
    typer.echo(f"State ready: {rt.ledger.path.parent}")

    if not no_test:
        typer.echo("Checking your model responds...")
        try:
            res = rt.router.complete(
                [{"role": "user", "content": "Reply with the single word: ready"}],
                role="cheap",
                agent="init-smoke",
                est_usd=0.001,
            )
            ok = "ready" in (res.text or "").lower()
            if ok:
                typer.echo(f"Model OK: {res.model} (cost ${res.cost_usd:.4f}).")
            else:
                typer.echo(f"Model replied unexpectedly: {res.text[:80]!r}")
                typer.echo("Setup is saved; you can still run `midas earn`.")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"Could not reach the model: {exc}")
            typer.echo("Setup is saved. Run `midas providers doctor` for details.")

    if no_launch:
        typer.echo('\nReady. Try:  midas earn "your niche"  (or: midas dashboard)')
        return

    _launch_console(rt, host=host, port=port, open_browser=True)


def _launch_console(
    rt: Any, *, host: str, port: int, open_browser: bool, show_link: bool = False
) -> None:
    """Start the dashboard in this process and open the browser already signed in.

    The session capability lives in the magic URL we hand to the OS browser. We do
    not show it in the terminal by default — the user just sees their dashboard
    open. ``show_link=True`` is the rescue path for the rare "no browser opened"
    case (``midas dashboard --show-link``).
    """
    import uvicorn

    from midas.flagship.dashboard import create_app

    deps = rt.dashboard_deps(allowed_host=f"{host}:{port}")
    token = deps.login_token.value
    url = f"http://{host}:{port}"
    magic = f"{url}/login?token={token}"
    typer.echo(f"\nMidas console opening at {url}")
    if show_link:
        typer.echo(f"Direct link: {magic}")
    if open_browser:
        with suppress(Exception):
            import threading
            import webbrowser

            threading.Timer(0.6, lambda: webbrowser.open(magic)).start()
    typer.echo("Press Ctrl+C to stop.")
    uvicorn.run(create_app(deps, bind_host=host), host=host, port=port, log_level="warning")


@app.command()
def setup(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Initialize local state, signing key, memory, cache, approvals, and ledger.

    Also seeds ``config/providers.yml`` from the example if missing, so the LLM
    cascade boots without a first-run "all models failed" surprise.
    """
    from shutil import copyfile

    from midas.flagship.runtime import build_runtime

    cfg = Path(base_dir) / "config"
    providers = cfg / "providers.yml"
    example = cfg / "providers.example.yml"
    if not providers.exists() and example.exists():
        copyfile(example, providers)
        typer.echo(f"Seeded {providers.name} from providers.example.yml")

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
    no_launch: bool = typer.Option(
        False, "--no-launch", help="Don't open a browser window."
    ),
    show_link: bool = typer.Option(
        False,
        "--show-link",
        help="Print the magic sign-in link (rescue path if the browser fails to open).",
    ),
) -> None:
    """Start the local Midas Operator Console."""
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    _launch_console(
        rt, host=host, port=port, open_browser=not no_launch, show_link=show_link
    )


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
    magic = f"http://{host}:{port}/login?token={deps.login_token.value}"
    typer.echo(f"Midas console opening at http://{host}:{port}")
    telegram_config = rt.channels.telegram_config()
    if telegram_config is None:
        typer.echo("Telegram listener: not configured")
    else:
        typer.echo("Telegram listener: configured")
    with suppress(Exception):
        import threading
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(magic)).start()

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
        help="Eval subset: 'all' (default), 'tau' for τ-bench rule adherence, "
        "or 'live' for τ-bench against a real local model (Ollama).",
    ),
    model: str = typer.Option(
        "", "--model", help="(--suite live only) override model, e.g. 'llama3.1:8b'."
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Run the deterministic Proof-First eval suite (or the live lane with --suite live)."""
    from midas.core.eval import render_report
    from midas.flagship.eval import build_suite

    if suite == "live":
        from midas.flagship.eval.live_eval import build_live_suite

        live_suite = build_live_suite(model=model or None)
        results = live_suite.run()
    else:
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
            raise typer.BadParameter("--suite must be 'all', 'tau', or 'live'")
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


@app.command()
def earn(
    niche: str = typer.Argument(..., help="The niche to chase, e.g. 'tools for plumbers'."),
    live: bool = typer.Option(False, "--live", help="Use real LLM/search plumbing."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Closed cash loop: scan → prepare landing → queue approval → (operator ships).

    Compared to ``midas scan``, ``midas earn`` also asks the toolset for one
    cash-shaped artifact (``landing.draft``) sized for the picked move. It goes
    through Sentinel → ``ApprovalQueue`` like any other gated tool — nothing is
    executed inline. After running, use ``midas approvals`` + ``midas execute``
    to ship it.
    """
    from midas.flagship.flows.cash_loop import CashLoop
    from midas.flagship.flows.demo import demo_candidates
    from midas.flagship.flows.render import render_report
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    run_id = f"earn:{niche}"
    toolset = rt.build_toolset(run_id=run_id)
    loop = CashLoop(
        toolset=toolset,
        memory=rt.memory,
        ledger=rt.ledger,
        approvals=rt.approvals,
    )
    if live:
        report = loop.run(
            niche,
            router=rt.router,
            search=rt.search,
            verifier=rt.verifier,
            run_id=run_id,
        )
    else:
        report = loop.run(niche, candidates=demo_candidates())

    rt.append_receipt(
        run_id=run_id,
        agent="cli",
        tool="earn",
        inputs={"niche": niche, "live": live},
        outputs={
            "daily_move": bool(report.move),
            "artifacts_queued": len(report.artifacts),
            "feedback_applied": not report.feedback.is_zero,
        },
    )
    typer.echo(render_report(report.scan))
    if report.feedback.reasons:
        typer.echo("\nFeedback bias from past cash:")
        for r in report.feedback.reasons:
            typer.echo(f"  - {r}")
    if report.artifacts:
        typer.echo("\nQueued artifacts (awaiting approval):")
        for art in report.artifacts:
            typer.echo(f"  - {art.tool} (approval #{art.approval_id})")
    typer.echo(
        "\nMIDAS prepared the move. Nothing shipped. Approve with `midas approvals approve <id>` "
        "then `midas execute <id>`."
    )


@app.command()
def advise(
    vault: str = typer.Argument(
        ..., help="Path to your Obsidian vault (or any folder of Markdown notes)."
    ),
    live: bool = typer.Option(
        False, "--live", help="Use the LLM to propose 3 ranked cash moves."
    ),
    start: bool = typer.Option(
        False, "--start",
        help="After ranking, immediately queue an `earn` cycle on the top move.",
    ),
    limit: int = typer.Option(50, "--limit", help="Max notes to scan."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Partner mode — reads your vault, ranks 3 cash moves, optionally launches one.

    Reads notes locally (no upload). Symlinks that escape the vault are refused.
    With ``--live``: asks the LLM for **3 ranked moves**, each citing the source
    note(s) and stating the shortest path to $1. With ``--start``: queues a full
    cash cycle on move #1 (`midas earn`-equivalent, gated as always).
    """
    from midas.flagship.flows.cash_loop import CashLoop
    from midas.flagship.flows.demo import demo_candidates
    from midas.flagship.obsidian import projects, scan_vault, summarize_vault
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    notes = scan_vault(vault, limit=limit)
    summary = summarize_vault(notes)
    typer.echo(summary)
    typer.echo("")

    proj = projects(notes)
    if not proj:
        typer.echo(
            "No project notes detected. Tag one note with #project (or place it "
            "in a `projects/` folder) and run again."
        )
        return

    if not live:
        typer.echo(
            f"\nFound {len(proj)} project(s). Run with --live to get 3 ranked cash moves."
        )
        return

    # Live advisor — single LLM call, asks for 3 RANKED moves with citations.
    project_block = "\n".join(
        f"### {n.title}\nFile: {n.path.name}\n\n{n.excerpt[:800]}" for n in proj[:5]
    )
    prompt = (
        "You are the operator's business co-pilot. Based ONLY on the project "
        "notes below, propose THREE next cash moves, ranked from shortest to "
        "longest path to $1 of revenue. For each move use this format:\n"
        "\n"
        "## Move N (rank N): <one-line move title>\n"
        "- Project: <which project, file name>\n"
        "- Audience: <who exactly>\n"
        "- Channel: <where to reach them>\n"
        "- Deliverable: <what artifact MIDAS should prepare>\n"
        "- Estimated time: <hours of operator work>\n"
        "- Why this rank: <one sentence>\n"
        "\n"
        "No revenue promises. Cite file names you used. Under 400 words total.\n\n"
        + project_block
    )
    res = rt.router.complete(
        [{"role": "system", "content": "Honest, terse business co-pilot."},
         {"role": "user", "content": prompt}],
        role="cheap", agent="advise",
    )
    run_id = f"advise:{Path(vault).name}"
    rt.append_receipt(
        run_id=run_id,
        agent="cli",
        tool="advise",
        inputs={"vault": str(vault), "n_projects": len(proj), "n_notes": len(notes)},
        outputs={"model": res.model, "cost_usd": res.cost_usd},
    )
    typer.echo("\n── 3 ranked cash moves ─────────────────────────────────────")
    typer.echo(res.text)
    typer.echo(f"\n(receipted; cost: ${res.cost_usd:.4f})")

    if not start:
        typer.echo(
            "\nTip: `midas advise <vault> --live --start` queues an `earn` cycle "
            "on Move #1 right after ranking."
        )
        return

    # --start: queue an earn cycle for the top project (heuristic: use the
    # title of the most-recently-modified project note as the niche string).
    top = proj[0]
    typer.echo(f"\n── Starting earn cycle on: {top.title}  [src: {top.path.name}] ──")
    earn_run_id = f"earn:advise:{top.path.stem}"
    toolset = rt.build_toolset(run_id=earn_run_id)
    loop = CashLoop(
        toolset=toolset, memory=rt.memory, ledger=rt.ledger, approvals=rt.approvals,
    )
    report = loop.run(top.title, candidates=demo_candidates())
    if report.move:
        typer.echo(f"  - move picked: {report.move.candidate.name}")
    typer.echo(f"  - artifacts queued: {len(report.artifacts)}")
    for art in report.artifacts:
        typer.echo(f"      * {art.tool} → approval #{art.approval_id}")
    typer.echo("\nReview with `midas approvals list`. Nothing was shipped.")


@app.command()
def heartbeat(
    niches: str = typer.Argument(
        ..., help="Comma-separated list of niches, e.g. 'plumbers,electricians'."
    ),
    live: bool = typer.Option(False, "--live", help="Use real LLM/search plumbing."),
    max_niches: int = typer.Option(10, "--max-niches"),
    max_artifacts: int = typer.Option(20, "--max-artifacts"),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Autonomous PREPARATION pass across multiple niches.

    Stacks signed approvals for the operator to ship. Never executes, never
    auto-approves. Bounded by ``--max-niches`` and ``--max-artifacts``.

    For recurring runs, install via ``midas schedule recipe``.
    """
    from midas.flagship.flows.cash_loop import CashLoop
    from midas.flagship.flows.demo import demo_candidates
    from midas.flagship.flows.heartbeat import CashHeartbeat
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    parsed = [n.strip() for n in niches.split(",") if n.strip()]
    if not parsed:
        raise typer.BadParameter("at least one niche is required")
    run_id = f"heartbeat:{','.join(parsed)[:60]}"
    loop = CashLoop(
        toolset=rt.build_toolset(run_id=run_id),
        memory=rt.memory,
        ledger=rt.ledger,
        approvals=rt.approvals,
    )
    hb = CashHeartbeat(
        loop=loop,
        router=rt.router if live else None,
        search=rt.search if live else None,
        verifier=rt.verifier if live else None,
        max_niches=max_niches,
        max_artifacts=max_artifacts,
    )
    # Offline path uses demo candidates for every niche (honest fallback).
    cands_map = (
        None if live else {n: demo_candidates() for n in parsed}
    )
    report = hb.run_once(parsed, live=live, candidates_by_niche=cands_map)

    rt.append_receipt(
        run_id=run_id,
        agent="cli",
        tool="heartbeat",
        inputs={"niches": parsed, "live": live},
        outputs={
            "runs": len(report.runs),
            "approvals_queued": report.approvals_queued,
            "stopped_reason": report.stopped_reason,
            "elapsed_seconds": report.elapsed_seconds,
        },
    )
    typer.echo(
        f"Heartbeat done: {len(report.runs)} run(s), {report.approvals_queued} "
        f"approval(s) queued in {report.elapsed_seconds:.1f}s ({report.stopped_reason})."
    )
    for niche, n in report.queued_per_niche.items():
        typer.echo(f"  - {niche}: {n} artifact(s) prepared")
    typer.echo(
        "\nNothing was shipped. Review with `midas approvals list`."
    )


@app.command()
def pipeline(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Show every cash move's stage (awaiting_approval / shipped / outcome_recorded).

    All rows are derived from the receipts ledger, the approval queue and
    ``MemoryKind.RESULT``. No hidden state.
    """
    from midas.flagship.flows.cash_loop import CashLoop
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    loop = CashLoop(
        toolset=rt.build_toolset(),
        memory=rt.memory,
        ledger=rt.ledger,
        approvals=rt.approvals,
    )
    rows = loop.pipeline()
    if not rows:
        typer.echo("Pipeline is empty. Run `midas earn <niche>` first.")
        return
    typer.echo(
        f"{'run_id':<40} {'stage':<20} {'pending':>8} {'cost':>10} {'rev':>10} {'net':>10}"
    )
    typer.echo("-" * 100)
    for r in rows:
        # Truncate by GRAPHEME-ish width (ASCII-safe ellipsis) — never inside a UTF-8 char.
        rid = r["run_id"]
        if len(rid) > 40:
            rid = rid[:37].rstrip() + "..."
        typer.echo(
            f"{rid:<40} {r['stage']:<20} {r['approvals_pending']:>8}"
            f" {r['cost_usd']:>10.4f} {r['revenue_usd']:>10.2f} {r['net_usd']:>10.2f}"
        )


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
    # Accept any case ("USER", "user", "User") + suggest valid kinds on typo.
    try:
        mem_kind = MemoryKind(kind.lower().strip())
    except ValueError as exc:
        valid = ", ".join(k.value for k in MemoryKind)
        raise typer.BadParameter(
            f"unknown memory kind {kind!r}. Try: {valid}"
        ) from exc
    entry = rt.memory.remember(
        mem_kind,
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
def demo(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
    out_dir: str = typer.Option(
        "demo-output", "--out", help="Workspace dir where the demo writes its artifacts."
    ),
) -> None:
    """Zero-config, fully-offline demo. Produces an artifact + a proof link in one go.

    Runs WITHOUT a configured LLM provider — uses the deterministic refuse-planner
    fallback so the loop always produces an ``artifact.text`` proposal. The
    operator can then run ``midas execute <approval_id>`` to materialize it and
    ``midas proof export demo-proof.html`` to share the signed receipt chain.
    """
    from midas.flagship.agent import AgentLoop, build_default_toolset
    from midas.flagship.agent.execute import execute_approved_step
    from midas.flagship.agent.loop import offline_artifact_planner
    from midas.flagship.proof_link import export_proof_link
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    if rt.fs_guard is None:
        raise typer.BadParameter("fs_guard not initialized — run `midas setup` first")

    # The demo writes its artifact into a sub-directory of the workspace so it
    # does not collide with anything the operator already has.
    workspace_target = rt.fs_guard.resolve(out_dir)
    workspace_target.mkdir(parents=True, exist_ok=True)

    toolset = build_default_toolset(
        sentinel=rt.sentinel, guard=rt.fs_guard,
        ledger=rt.ledger, approvals=rt.approvals,
        run_id="demo:run",
        search=rt.search, fetcher=rt.fetcher, verifier=rt.verifier,
    )
    loop = AgentLoop(
        toolset=toolset,
        planner=offline_artifact_planner,  # deterministic, no LLM, never refuses
        max_steps=3,
        agent_name="demo",
    )
    transcript = loop.run("Produce a one-page MIDAS proof-of-concept artifact.")
    typer.echo(json.dumps(transcript.to_json(), indent=2, ensure_ascii=False))

    # Auto-approve the one artifact the refuse-planner queues — the demo's whole
    # point is to surface the END-TO-END flow with no human in the loop.
    if not transcript.queued_approvals:
        typer.echo("Demo produced no approvals — nothing to execute.")
        raise typer.Exit(code=1)
    approval_id = transcript.queued_approvals[0]
    rt.approvals.approve(approval_id, by="cli")
    request = rt.approvals.get(approval_id)
    if request is None:
        raise typer.BadParameter(f"approval #{approval_id} vanished")
    result = execute_approved_step(rt, request)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    # Export the proof link for this run.
    proof_path = rt.fs_guard.resolve(f"{out_dir}/demo-proof.html")
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(
        export_proof_link(
            rt.ledger, public_key_hex=rt.ledger.public_key_hex, run_id="demo:run"
        ),
        encoding="utf-8",
    )
    typer.echo(f"\nProof link: {proof_path}")
    typer.echo("Open it in any browser — no install required.")


@app.command()
def replay(
    run_id: str = typer.Argument(
        "",
        help="run_id from a past receipt. Pass nothing to list all known run_ids.",
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Reconstruct a past run's transcript shape from its signed receipts.

    Without arguments, lists every run_id present in the receipt ledger so you
    can pick one (no more 'No receipts for ...' frustration).
    """
    from midas.flagship.replay import format_replay, replay_run
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    if not run_id.strip():
        seen: dict[str, int] = {}
        try:
            for r in rt.ledger:
                rid = r.body.run_id
                seen[rid] = seen.get(rid, 0) + 1
        except TypeError:
            pass
        if not seen:
            typer.echo("No runs in the ledger yet. Try `midas earn <niche>` first.")
            return
        typer.echo(f"{'run_id':<60} {'receipts':>10}")
        typer.echo("-" * 72)
        for rid, n in sorted(seen.items()):
            typer.echo(f"{rid[:60]:<60} {n:>10}")
        typer.echo("\nReplay one with: midas replay '<run_id>'")
        return
    transcript = replay_run(rt.ledger, run_id)
    typer.echo(format_replay(transcript))


@skills_app.command("export")
def skills_export(
    name: str = typer.Argument(..., help="Local skill name (slug) to bundle."),
    output: str = typer.Argument(..., help="Output directory for the signed bundle."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Sign a local skill and export it as a portable, verifiable bundle."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.signed_skills import export_signed_skill

    rt = build_runtime(base_dir)
    if rt.skill_registry is None:
        raise typer.BadParameter("skill registry not initialized")
    source = rt.skill_registry.skills_dir / name
    if not source.is_dir():
        raise typer.BadParameter(f"unknown local skill: {name}")
    signer = rt.ledger._signer  # noqa: SLF001 - reuse the install's signing identity
    dst = rt.fs_guard.resolve(output) if rt.fs_guard else Path(output)
    export_signed_skill(source, dst, signer, name=name)
    rt.append_receipt(
        run_id=f"skills:export:{name}",
        agent="cli",
        tool="skills.export",
        inputs={"name": name, "output": str(dst)},
        outputs={"public_key_hex": signer.public_key_hex},
    )
    typer.echo(f"Wrote signed bundle to {dst} (pub: {signer.public_key_hex[:16]}…)")


@skills_app.command("verify")
def skills_verify(
    bundle: str = typer.Argument(..., help="Path to a signed skill bundle."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Verify a signed skill bundle's manifest, file hashes, and signature."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.signed_skills import verify_signed_skill

    rt = build_runtime(base_dir)
    target = rt.fs_guard.resolve(bundle) if rt.fs_guard else Path(bundle)
    result = verify_signed_skill(target)
    if result.ok:
        typer.echo(
            f"OK — {result.manifest.name if result.manifest else '?'} "
            f"(pub: {(result.public_key_hex or '')[:16]}…)"
        )
    else:
        typer.echo(f"FAIL — {result.error}")
        raise typer.Exit(code=1)


@skills_app.command("import")
def skills_import(
    bundle: str = typer.Argument(..., help="Path to a verified signed skill bundle."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Queue approval to install a signed skill bundle (verifies first)."""
    from midas.flagship.runtime import build_runtime
    from midas.flagship.signed_skills import verify_signed_skill

    rt = build_runtime(base_dir)
    target = rt.fs_guard.resolve(bundle) if rt.fs_guard else Path(bundle)
    result = verify_signed_skill(target)
    if not result.ok:
        raise typer.BadParameter(f"verification failed: {result.error}")
    req = rt.approvals.enqueue(
        run_id=f"skills:import:{result.manifest.name if result.manifest else 'unknown'}",
        agent="cli",
        tool="skills.import_signed",
        action="install_skill_or_tool",
        summary=f"Install signed skill {result.manifest.name if result.manifest else 'unknown'}",
        payload={
            "bundle": str(target),
            "public_key_hex": result.public_key_hex,
            "manifest_name": result.manifest.name if result.manifest else None,
        },
    )
    rt.append_receipt(
        run_id=f"skills:import:{result.manifest.name if result.manifest else 'unknown'}",
        agent="cli",
        tool="skills.import_signed",
        decision=Decision.QUEUE_APPROVAL,
        inputs={"bundle": str(target)},
        outputs={"approval_id": req.id},
    )
    typer.echo(f"Verified. Approval queued: #{req.id}")


@app.command()
def roi(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Print a per-run ROI table — cost from receipts, revenue from outcomes."""
    from midas.flagship.roi import build_outcomes_index, compute_run_roi, format_roi_report
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    outcomes = build_outcomes_index(rt.memory)
    report = compute_run_roi(rt.ledger, outcomes)
    typer.echo(format_roi_report(report))


@proof_app.command("export")
def proof_export(
    output: str = typer.Argument(..., help="Path to write the proof-link HTML."),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Restrict the proof link to one run. Default = full chain."
    ),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Export a portable, offline-verifiable proof-link HTML for the operator's chain."""
    from midas.flagship.proof_link import export_proof_link
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    html = export_proof_link(
        rt.ledger,
        public_key_hex=rt.ledger.public_key_hex,
        run_id=run_id,
    )
    if rt.fs_guard is not None:
        target = rt.fs_guard.resolve(output)
    else:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    rt.append_receipt(
        run_id=run_id or "proof:full",
        agent="cli",
        tool="proof.export",
        inputs={"output": str(target), "run_id": run_id},
        outputs={"bytes": len(html), "path": str(target)},
    )
    typer.echo(f"Wrote {target}")


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


# ── MCP commands ────────────────────────────────────────────────────────────


@mcp_app.command("serve")
def mcp_serve(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
    name: str = typer.Option("midas", "--name", help="MCP server name."),
) -> None:
    """Run MIDAS as an MCP server over stdio (for Claude Desktop / Cursor)."""
    from midas.flagship.mcp.server import run_stdio
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    run_stdio(rt, name=name)


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Logical name, e.g. 'filesystem'."),
    command: str = typer.Argument(..., help="Executable, e.g. 'npx' or 'uvx'."),
    arg: Annotated[
        list[str] | None,
        typer.Option("--arg", "-a", help="Argument (repeat for each)."),
    ] = None,
    env: Annotated[
        list[str] | None,
        typer.Option("--env", "-e", help="KEY=value env var (repeat for each)."),
    ] = None,
    note: str = typer.Option("", "--note", help="Free-form note for the operator."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Add or update an external MCP server in the registry."""
    from midas.flagship.mcp.config import McpServerConfig, upsert_server
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    env_dict: dict[str, str] = {}
    for raw in env or []:
        if "=" not in raw:
            raise typer.BadParameter(f"invalid --env: {raw!r} (use KEY=value)")
        k, v = raw.split("=", 1)
        env_dict[k.strip()] = v
    cfg = McpServerConfig(
        name=name, command=command, args=list(arg or []), env=env_dict, note=note,
    )
    upsert_server(rt.state_dir, cfg)
    typer.echo(f"Added MCP server: {name} ({command} {' '.join(arg or [])})")
    typer.echo(f"  → registered in {rt.state_dir / 'mcp_servers.yml'}")


@mcp_app.command("list")
def mcp_list(
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """List registered external MCP servers."""
    from midas.flagship.mcp.config import load_servers_file
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    file = load_servers_file(rt.state_dir)
    if not file.servers:
        typer.echo("No MCP servers registered. Add one with `midas mcp add <name> <command>`.")
        return
    for s in file.servers:
        status = "enabled" if s.enabled else "DISABLED"
        typer.echo(f"  - {s.name}  ({status})  {s.command} {' '.join(s.args)}")
        if s.note:
            typer.echo(f"      note: {s.note}")


@mcp_app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Remove an external MCP server."""
    from midas.flagship.mcp.config import remove_server
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    remove_server(rt.state_dir, name)
    typer.echo(f"Removed MCP server: {name}")


@mcp_app.command("test")
def mcp_test(
    name: str = typer.Argument(..., help="Server name to probe."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Probe an external MCP server: connect, list its tools, disconnect.

    No tool is called and no approval is queued. Use this to verify the server
    actually starts and to discover what tools it exposes.
    """
    from midas.flagship.mcp.client import list_tools
    from midas.flagship.mcp.config import load_servers_file
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    file = load_servers_file(rt.state_dir)
    cfg = next((s for s in file.servers if s.name == name), None)
    if cfg is None:
        raise typer.BadParameter(f"unknown MCP server: {name!r}")
    try:
        tools = list_tools(cfg)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Connection FAILED: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"OK — {cfg.name} exposes {len(tools)} tool(s):")
    for t in tools:
        typer.echo(f"  - {t.name}: {t.description[:80]}")


@mcp_app.command("import")
def mcp_import(
    name: str = typer.Argument(..., help="Server name to import tools from."),
    base_dir: str = typer.Option(".", "--base-dir", help="Project dir holding config/."),
) -> None:
    """Connect to an MCP server, list its tools, and queue a single APPROVE-tier
    call so the operator can see what will get gated.

    The actual tools are registered at runtime by ``midas earn`` / ``midas do``
    when an MCP server is configured. This command is a diagnostic.
    """
    from midas.flagship.mcp.client import list_tools, register_external_mcp_tools
    from midas.flagship.mcp.config import load_servers_file
    from midas.flagship.runtime import build_runtime

    rt = build_runtime(base_dir)
    file = load_servers_file(rt.state_dir)
    cfg = next((s for s in file.servers if s.name == name), None)
    if cfg is None:
        raise typer.BadParameter(f"unknown MCP server: {name!r}")
    summaries = list_tools(cfg)
    toolset = rt.build_toolset(run_id=f"mcp:import:{name}")
    registered = register_external_mcp_tools(toolset, cfg, summaries=summaries)
    typer.echo(f"Imported {len(registered)} tool(s) from {cfg.name}:")
    for n in registered:
        typer.echo(f"  - {n}  (action=call_external_mcp, taint=UNTRUSTED, approval-gated)")
    typer.echo(
        "\nThese tools are now visible inside this process. Persistent registration "
        "happens automatically in `midas earn` / `midas do` when an MCP server is in "
        f"{rt.state_dir / 'mcp_servers.yml'}."
    )


if __name__ == "__main__":
    app()
