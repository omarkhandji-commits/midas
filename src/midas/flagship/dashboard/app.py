"""FastAPI dashboard — local-only, owner-only, Proof-First receipts on every action.

Hard rules enforced at the app layer (in addition to the per-request defenses):
- the dashboard MUST be bound to 127.0.0.1 (loopback). The runtime refuses 0.0.0.0;
- every endpoint except `/login` and static assets requires a verified session;
- every state-changing endpoint requires CSRF token + Origin check;
- every approval resolve is dispatched through the SAME ApprovalQueue used by all
  other channels — the dashboard does not have a privileged side channel;
- nothing leaves the box: no CDN, no analytics, no font fetch, no remote scripts.

This module exposes `create_app(...)` returning a configured FastAPI instance so
tests can mount it without starting a server.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from midas.core.approvals import ApprovalError, ApprovalQueue
from midas.core.budget import BudgetExceeded
from midas.core.receipts.models import Decision
from midas.flagship.chat import run_chat
from midas.flagship.outcomes import Outcome, ingest_outcome

from .auth import LoginToken, Sessions
from .events import event_stream, take_snapshot
from .security import (
    csrf_ok,
    is_state_changing,
    issue_csrf_token,
    make_nonce,
    origin_ok,
    security_headers,
)

_HERE = Path(__file__).resolve().parent
_TEMPLATES = _HERE / "templates"
_STATIC = _HERE / "static"
_SPA_INDEX = _STATIC / "app" / "index.html"

# Paths that must NEVER be swallowed by the SPA catch-all (kept here to make the
# allow-list explicit and reviewable). Includes FastAPI's auto-disabled doc paths
# so /docs, /redoc, /openapi.json keep their 404 (no fingerprinting surface).
_NON_SPA_PREFIXES: tuple[str, ...] = (
    "api/", "static/", "events", "login", "snapshot", "outcomes",
    "approvals/", "dashboard", "docs", "redoc", "openapi.json",
)


def _spa_available() -> bool:
    """The built SPA exists on disk. Lets us fall back to Jinja during tests/CI."""
    return _SPA_INDEX.is_file()

SESSION_COOKIE = "midas_session"
CSRF_COOKIE = "midas_csrf"
CSRF_HEADER = "X-MIDAS-CSRF"


@dataclass
class DashboardDeps:
    """Everything the dashboard needs. Wired by the runtime, mocked by tests."""

    queue: ApprovalQueue
    sessions: Sessions
    login_token: LoginToken
    allowed_hosts: set[str]
    ledger: Any = None  # ReceiptLedger for the cost meter (optional)
    memory: Any = None  # MemoryStore — required for /outcomes; optional otherwise
    competitors: Any = None  # CompetitorStore for Market Radar APIs
    providers: Any = None  # ProviderManager for keychain-backed provider setup
    settings_store: Any = None  # SettingsStore for local dashboard settings
    router: Any = None  # LLMRouter for optional live provider tests
    sentinel: Any = None  # Sentinel gate for chat-proposed approval cards
    search: Any = None  # SearchAdapter for live missions
    verifier: Any = None  # SourceVerifier for live missions
    channels: Any = None  # ChannelManager for owner-gated channel setup
    fetcher: Any = None  # Fetcher used by Market Radar snapshot endpoints (optional)
    schedule_store: Any = None  # ScheduleStore for recipe CRUD (optional)
    skill_registry: Any = None  # SkillRegistry for skills CRUD (optional)
    fs_guard: Any = None  # FsGuard for the Do-mode executor (optional)
    chat_est_usd: float = 0.02
    sse_interval_seconds: float = 1.5  # tests can shorten via deps; UI default is 1.5s


def create_app(deps: DashboardDeps, *, bind_host: str = "127.0.0.1") -> FastAPI:
    if bind_host not in ("127.0.0.1", "localhost", "::1"):
        # Hard fail-closed: refuse to wire an app meant for remote exposure.
        raise ValueError(
            f"dashboard MUST bind to loopback (got {bind_host!r}). "
            "Remote exposure is not supported by design."
        )

    templates = Jinja2Templates(directory=str(_TEMPLATES))
    # Jinja2 autoescape is ON by default for HTML — XSS guard for everything we render.

    app = FastAPI(title="MIDAS Dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.middleware("http")
    async def _security(request: Request, call_next):
        # CSRF + Origin gate BEFORE the handler runs.
        if is_state_changing(request.method) and request.url.path != "/login":
            if not origin_ok(origin=request.headers.get("origin"),
                             allowed_hosts=deps.allowed_hosts):
                return _json(403, {"error": "bad origin"})
            if not csrf_ok(
                cookie_token=request.cookies.get(CSRF_COOKIE),
                header_token=request.headers.get(CSRF_HEADER),
            ):
                return _json(403, {"error": "csrf"})

        nonce = make_nonce()
        request.state.nonce = nonce
        response: Response = await call_next(request)
        for k, v in security_headers(nonce=nonce).items():
            response.headers[k] = v
        return response

    def _require_session(request: Request) -> None:
        cookie = request.cookies.get(SESSION_COOKIE)
        if not deps.sessions.verify(cookie):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")

    # ── routes ────────────────────────────────────────────────────────────────
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, token: str | None = None) -> Any:
        # Magic-link path: ``midas init`` opens the browser on /login?token=<one-time>
        # so first-time users land already authenticated. Token is single-use and
        # never written to disk — patron Jupyter, loopback-only.
        if token:
            if deps.login_token.consume(token):
                return _issue_session_redirect(request)
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "nonce": request.state.nonce,
                    "error": "This link is no longer valid. Paste the token below.",
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return templates.TemplateResponse(
            request, "login.html", {"nonce": request.state.nonce}
        )

    def _issue_session_redirect(request: Request) -> Response:
        session = deps.sessions.issue()
        csrf = issue_csrf_token()
        resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        resp.set_cookie(SESSION_COOKIE, session, httponly=True, samesite="strict")
        resp.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="strict")
        return resp

    @app.post("/login")
    def login_submit(request: Request, token: str = Form(...)) -> Response:
        if not deps.login_token.consume(token):
            # Constant-time consume already; rate-limit the surface anyway.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
        session = deps.sessions.issue()
        csrf = issue_csrf_token()
        resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        # Session: HttpOnly so JS cannot read it. SameSite=Strict blocks cross-origin
        # navigation from carrying it. `secure` would require HTTPS — on loopback,
        # the browser treats 127.0.0.1 as secure context for cookie purposes.
        resp.set_cookie(SESSION_COOKIE, session, httponly=True, samesite="strict")
        # CSRF cookie must be readable by JS to put into the X-MIDAS-CSRF header
        # (double-submit pattern); SameSite=Strict still blocks cross-site sends.
        resp.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="strict")
        return resp

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Any:
        _require_session(request)
        # Prefer the React SPA when it is built into static/app/. The Jinja shell is
        # still shipped as a graceful fallback for tests/CI environments without Node.
        if _spa_available():
            return HTMLResponse(_SPA_INDEX.read_text(encoding="utf-8"))
        pending = deps.queue.pending()
        receipts = list(deps.ledger) if deps.ledger is not None else []
        spent = round(sum(r.body.cost_usd for r in receipts), 6)
        memory_count = len(deps.memory.recall(limit=10_000)) if deps.memory is not None else 0
        competitor_count = len(deps.competitors.list()) if deps.competitors is not None else 0
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "nonce": request.state.nonce,
                "pending": pending,
                "spent_usd": spent,
                "receipt_count": len(receipts),
                "memory_count": memory_count,
                "competitor_count": competitor_count,
            },
        )

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard_alias(request: Request) -> Any:
        return home(request)

    @app.post("/approvals/{req_id}/approve")
    def approve(request: Request, req_id: int) -> Response:
        _require_session(request)
        return _resolve(deps, req_id, approve=True)

    @app.post("/approvals/{req_id}/reject")
    def reject(request: Request, req_id: int) -> Response:
        _require_session(request)
        return _resolve(deps, req_id, approve=False)

    @app.get("/api/runs")
    def api_runs(request: Request) -> Response:
        _require_session(request)
        receipts = list(deps.ledger) if deps.ledger is not None else []
        runs: dict[str, dict[str, Any]] = {}
        for r in receipts:
            item = runs.setdefault(
                r.body.run_id,
                {
                    "run_id": r.body.run_id,
                    "receipts": 0,
                    "cost_usd": 0.0,
                    "latest_ts": "",
                    "started_ts": r.body.ts,
                    "agents": set(),
                    "tools": set(),
                    "pending_approval": False,
                    "denied": False,
                },
            )
            item["receipts"] += 1
            item["cost_usd"] = round(float(item["cost_usd"]) + r.body.cost_usd, 6)
            item["latest_ts"] = r.body.ts
            item["agents"].add(r.body.agent)
            item["tools"].add(r.body.tool)
            decision = r.body.decision.value
            if decision == "queue_approval":
                item["pending_approval"] = True
            elif decision == "deny":
                item["denied"] = True
        rows = []
        for item in runs.values():
            row = dict(item)
            row["agents"] = sorted(item["agents"])
            row["tools"] = sorted(item["tools"])
            if row["denied"]:
                row["status"] = "denied"
            elif row["pending_approval"]:
                row["status"] = "awaiting_approval"
            else:
                row["status"] = "ok"
            rows.append(row)
        rows.sort(key=lambda r: r.get("latest_ts", ""), reverse=True)
        return _json(200, {"runs": rows[:50]})

    @app.get("/api/proofs")
    def api_proofs(request: Request) -> Response:
        _require_session(request)
        receipts = list(deps.ledger) if deps.ledger is not None else []
        chain: dict[str, Any] = {"ok": True, "count": len(receipts), "error": None}
        if deps.ledger is not None:
            try:
                from midas.core.receipts import verify_chain

                verified = verify_chain(deps.ledger.path, deps.ledger.public_key_hex)
                chain = {"ok": verified.ok, "count": verified.count, "error": verified.error}
            except Exception:
                chain = {"ok": False, "count": len(receipts), "error": "verify failed"}
        proofs = [
            {
                "seq": r.body.seq,
                "run_id": r.body.run_id,
                "agent": r.body.agent,
                "tool": r.body.tool,
                "decision": r.body.decision.value,
                "hash": r.hash,
                "prev_hash": r.body.prev_hash,
                "ts": r.body.ts,
            }
            for r in receipts[-100:]
        ]
        return _json(200, {"proofs": proofs, "chain": chain})

    @app.get("/api/approvals")
    def api_approvals(request: Request) -> Response:
        _require_session(request)
        return _json(200, {"pending": [_approval_json(r) for r in deps.queue.pending()]})

    @app.post("/api/approvals/{req_id}/approve")
    def api_approve(request: Request, req_id: int) -> Response:
        _require_session(request)
        return _resolve(deps, req_id, approve=True)

    @app.post("/api/approvals/{req_id}/reject")
    def api_reject(request: Request, req_id: int) -> Response:
        _require_session(request)
        return _resolve(deps, req_id, approve=False)

    @app.get("/api/memory/search")
    def api_memory_search(request: Request, q: str = "", kind: str | None = None) -> Response:
        _require_session(request)
        if deps.memory is None:
            return _json(503, {"error": "memory disabled"})
        try:
            from midas.core.memory import MemoryKind

            rows = deps.memory.recall(
                kind=MemoryKind(kind) if kind else None,
                query=q or None,
                limit=50,
            )
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, {"memory": [_memory_json(r) for r in rows]})

    @app.get("/api/competitors")
    def api_competitors(request: Request) -> Response:
        _require_session(request)
        if deps.competitors is None:
            return _json(503, {"error": "competitors disabled"})
        return _json(200, {"competitors": [c.__dict__ for c in deps.competitors.list()]})

    @app.post("/api/competitors")
    async def api_competitors_add(request: Request) -> Response:
        _require_session(request)
        if deps.competitors is None:
            return _json(503, {"error": "competitors disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            name = str(body.get("name") or "").strip()
            url = str(body.get("url") or "").strip()
            notes = str(body.get("notes") or "").strip()
            if not name or not url:
                return _json(400, {"error": "name and url required"})
            if not (url.startswith("http://") or url.startswith("https://")):
                return _json(400, {"error": "url must start with http:// or https://"})
        except Exception:
            return _json(400, {"error": "invalid json"})
        comp = deps.competitors.add(name, url, notes=notes)
        _receipt(
            deps,
            tool="competitors.add",
            inputs={"name": name, "url": url},
            outputs={"competitor_id": comp.id},
        )
        return _json(200, {"ok": True, "competitor": comp.__dict__})

    @app.delete("/api/competitors/{competitor_id}")
    def api_competitors_delete(request: Request, competitor_id: int) -> Response:
        _require_session(request)
        if deps.competitors is None:
            return _json(503, {"error": "competitors disabled"})
        removed = deps.competitors.delete(competitor_id)
        if not removed:
            return _json(404, {"error": "competitor not found"})
        _receipt(
            deps,
            tool="competitors.delete",
            inputs={"competitor_id": competitor_id},
            outputs={"removed": True},
        )
        return _json(200, {"ok": True})

    @app.get("/api/competitors/{competitor_id}/snapshots")
    def api_competitor_snapshots(request: Request, competitor_id: int) -> Response:
        _require_session(request)
        if deps.competitors is None:
            return _json(503, {"error": "competitors disabled"})
        comp = deps.competitors.get(competitor_id)
        if comp is None:
            return _json(404, {"error": "competitor not found"})
        snaps = deps.competitors.snapshots(competitor_id)
        return _json(
            200,
            {
                "competitor": comp.__dict__,
                "snapshots": [_snapshot_json(s) for s in snaps],
            },
        )

    @app.post("/api/competitors/{competitor_id}/snapshot")
    def api_competitor_snapshot(request: Request, competitor_id: int) -> Response:
        _require_session(request)
        if deps.competitors is None:
            return _json(503, {"error": "competitors disabled"})
        if deps.search is None and deps.verifier is None:
            # We need a fetcher; reuse the runtime-provided HttpxFetcher via deps.
            pass
        comp = deps.competitors.get(competitor_id)
        if comp is None:
            return _json(404, {"error": "competitor not found"})
        fetcher = _resolve_fetcher(deps)
        if fetcher is None:
            return _json(503, {"error": "fetcher not configured"})
        snap = deps.competitors.snapshot(
            comp,
            fetcher=fetcher,
            memory=deps.memory,
            ledger=deps.ledger,
            run_id="dashboard:market",
        )
        return _json(200, {"ok": True, "snapshot": _snapshot_json(snap)})

    @app.post("/api/memory/add")
    async def api_memory_add(request: Request) -> Response:
        _require_session(request)
        if deps.memory is None:
            return _json(503, {"error": "memory disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            kind_raw = str(body.get("kind") or "").strip()
            key = str(body.get("key") or "").strip()
            content = str(body.get("content") or "").strip()
            proof_raw = str(body.get("proof_level") or "low").strip().lower()
            sources_in = body.get("sources") or []
            tags_in = body.get("tags") or []
            if not kind_raw or not key or not content:
                return _json(400, {"error": "kind, key and content required"})
            if not isinstance(sources_in, list) or not isinstance(tags_in, list):
                return _json(400, {"error": "sources and tags must be lists"})
            sources = [str(s).strip() for s in sources_in if str(s).strip()]
            tags = [str(t).strip() for t in tags_in if str(t).strip()]
        except Exception:
            return _json(400, {"error": "invalid json"})

        from midas.core.agents.summary import ProofLevel
        from midas.core.memory import MemoryKind

        try:
            kind = MemoryKind(kind_raw)
        except ValueError:
            return _json(400, {"error": f"invalid kind: {kind_raw}"})
        try:
            proof = ProofLevel(proof_raw)
        except ValueError:
            return _json(400, {"error": f"invalid proof_level: {proof_raw}"})
        if proof != ProofLevel.LOW and not sources:
            return _json(
                400,
                {"error": "MEDIUM/HIGH proof requires at least one source URL"},
            )
        entry = deps.memory.remember(
            kind, key, content, proof_level=proof, sources=sources, tags=tags
        )
        _receipt(
            deps,
            tool="memory.add",
            inputs={"kind": kind.value, "key": key},
            outputs={"id": entry.id, "proof_level": entry.proof_level.value},
        )
        return _json(200, {"ok": True, "entry": _memory_json(entry)})

    @app.get("/api/memory/history")
    def api_memory_history(request: Request, kind: str, key: str) -> Response:
        _require_session(request)
        if deps.memory is None:
            return _json(503, {"error": "memory disabled"})
        from midas.core.memory import MemoryKind

        try:
            kind_e = MemoryKind(kind)
        except ValueError:
            return _json(400, {"error": f"invalid kind: {kind}"})
        rows = deps.memory.history(kind_e, key)
        return _json(
            200,
            {
                "kind": kind_e.value,
                "key": key,
                "entries": [_memory_history_json(r) for r in rows],
            },
        )

    @app.get("/api/assets")
    def api_assets(request: Request) -> Response:
        _require_session(request)
        from midas.flagship.assets import ASSET_KEYS

        return _json(200, {"asset_types": list(ASSET_KEYS)})

    @app.post("/api/missions")
    async def api_missions(request: Request) -> Response:
        _require_session(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            niche = str(body.get("niche") or "").strip()
            live = bool(body.get("live") or False)
            mode = str(body.get("mode") or "deep")
            if not niche:
                return _json(400, {"error": "niche required"})
            if mode not in {"fast", "deep", "war-room"}:
                return _json(400, {"error": "invalid mode"})
        except Exception:
            return _json(400, {"error": "invalid json"})

        from midas.flagship.flows import run_scan, scan_niche
        from midas.flagship.flows.demo import demo_candidates

        run_id = f"mission:{uuid.uuid4().hex[:12]}"
        if live:
            if deps.router is None:
                return _json(503, {"error": "router disabled"})
            report = scan_niche(
                niche,
                router=deps.router,
                search=deps.search,
                verifier=deps.verifier,
                ledger=deps.ledger,
                memory=deps.memory,
                run_id=run_id,
                task_id=run_id,
                est_usd=deps.chat_est_usd,
            )
        else:
            report = run_scan(niche, demo_candidates(), ledger=deps.ledger, memory=deps.memory)
        approval_id = _queue_move_approval(deps, report, run_id=run_id)
        _receipt(
            deps,
            tool="missions.scan",
            inputs={"niche": niche, "live": live, "mode": mode},
            outputs={
                "daily_move": bool(report.daily_move),
                "proof_level": report.proof_level.value,
                "approval_id": approval_id,
            },
        )
        return _json(200, {"ok": True, "mission": _scan_report_json(report, run_id, approval_id)})

    @app.post("/api/assets/generate")
    async def api_assets_generate(request: Request) -> Response:
        _require_session(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            topic = str(body.get("topic") or "").strip()
            summary = str(body.get("summary") or topic).strip()
            live = bool(body.get("live") or False)
            if not topic:
                return _json(400, {"error": "topic required"})
        except Exception:
            return _json(400, {"error": "invalid json"})

        from midas.flagship.assets import heuristic_assets, llm_assets, simple_pdf_bytes

        candidate = _candidate_from_topic(topic, summary)
        if live:
            if deps.router is None:
                return _json(503, {"error": "router disabled"})
            assets = llm_assets(candidate, router=deps.router, run_id="assets:generate")
        else:
            assets = heuristic_assets(candidate)
        asset_json = assets.as_dict()
        pdfs = {
            key: {
                "filename": f"{key}.pdf",
                "media_type": "application/pdf",
                "base64": base64.b64encode(
                    simple_pdf_bytes(key.replace("_", " ").title(), asset_json[key])
                ).decode("ascii"),
            }
            for key in ("proposal_pdf", "invoice_pdf")
        }
        _receipt(
            deps,
            tool="assets.generate",
            inputs={"topic": topic, "live": live},
            outputs={"asset_count": len(asset_json), "pdf_count": len(pdfs)},
        )
        return _json(200, {"ok": True, "assets": asset_json, "pdfs": pdfs})

    @app.get("/api/channels")
    def api_channels(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        return _json(200, {"channels": deps.channels.list_statuses()})

    @app.get("/api/onboard/detect-ollama")
    def api_onboard_detect_ollama(request: Request) -> Response:
        """Best-effort local Ollama detection for the /start wizard.

        Returns the installed model list and a recommended pick. Failure to reach
        Ollama is not an error — we simply report no local model so the wizard
        falls back to "paste a cloud API key".
        """
        _require_session(request)
        from midas.flagship.onboard import detect_ollama, pick_ollama_model

        try:
            models = detect_ollama()
        except Exception:  # noqa: BLE001 — local network probe; never crash the UI
            models = []
        chosen = pick_ollama_model(models)
        return _json(200, {"models": models, "chosen": chosen})

    @app.get("/api/capabilities")
    def api_capabilities(request: Request) -> Response:
        """Serialise the registered toolset so the dashboard never drifts.

        Source of truth is ``build_default_toolset()`` — the same call the agent
        loop uses. Each entry carries the policy tier the Sentinel will apply at
        call time, so the UI can render an honest AUTO/APPROVE badge without
        hand-maintained lists. Tier reflects the *current* policy, not assumptions.
        """
        _require_session(request)
        if deps.sentinel is None or deps.fs_guard is None:
            return _json(503, {"error": "capabilities unavailable"})
        from midas.core.sentinel.risk_tiers import classify
        from midas.flagship.agent import build_default_toolset

        ts = build_default_toolset(
            sentinel=deps.sentinel,
            guard=deps.fs_guard,
            ledger=deps.ledger,
            approvals=deps.queue,
            run_id="capabilities-view",
            search=deps.search,
            fetcher=deps.fetcher,
            verifier=deps.verifier,
        )
        policy = deps.sentinel.policy
        items: list[dict[str, Any]] = []
        for tool in sorted(ts._tools.values(), key=lambda t: t.name):  # noqa: SLF001
            tier = classify(tool.action, policy).value
            items.append(
                {
                    "name": tool.name,
                    "action": tool.action,
                    "tier": tier,
                    "taint": tool.output_taint.value,
                    "has_egress": tool.has_egress,
                    "group": _capability_group(tool.name),
                }
            )
        return _json(200, {"tools": items})

    @app.get("/api/personas")
    def api_personas(request: Request) -> Response:
        """Return the persona presets that pre-configure the new-user wizard.

        Pure data, no secrets, no egress — safe to cache client-side.
        """
        _require_session(request)
        from midas.flagship.personas import list_personas, persona_as_dict

        return _json(
            200, {"personas": [persona_as_dict(p) for p in list_personas()]}
        )

    @app.get("/api/onboard/state")
    def api_onboard_state(request: Request) -> Response:
        """One-shot snapshot for the wizard: provider ready, channel ready, first action done.

        The wizard reads this on mount to resume at the right step if interrupted.
        """
        _require_session(request)
        has_provider = False
        if deps.providers is not None:
            has_provider = any(
                p.get("configured") for p in deps.providers.list_statuses()
            )
        has_channel = False
        if deps.channels is not None:
            has_channel = any(
                c.get("connected") for c in deps.channels.list_statuses()
            )
        # First action = any non-system receipt in the ledger.
        has_first_run = False
        if deps.ledger is not None:
            for r in deps.ledger:
                if r.body.run_id not in {"init", "setup", "dashboard"}:
                    has_first_run = True
                    break
        return _json(
            200,
            {
                "has_provider": has_provider,
                "has_channel": has_channel,
                "has_first_run": has_first_run,
            },
        )

    @app.post("/api/channels/telegram")
    async def api_channels_telegram_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            bot_token = str(body.get("bot_token") or "")
            owner_chat_id = str(body.get("owner_chat_id") or "")
            status_json = deps.channels.connect_telegram(
                bot_token=bot_token,
                owner_chat_id=owner_chat_id,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.telegram.connect",
            inputs={
                "token_supplied": bool(bot_token.strip()),
                "owner_supplied": bool(owner_chat_id.strip()),
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/telegram/test")
    def api_channels_telegram_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_telegram()
        _receipt(
            deps,
            tool="channels.telegram.test",
            inputs={"channel": "telegram"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/telegram")
    def api_channels_telegram_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_telegram().to_json()
        _receipt(
            deps,
            tool="channels.telegram.remove",
            inputs={"channel": "telegram"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/discord")
    async def api_channels_discord_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            bot_token = str(body.get("bot_token") or "")
            owner_user_id = str(body.get("owner_user_id") or "")
            guild_id = str(body.get("guild_id") or "")
            status_json = deps.channels.connect_discord(
                bot_token=bot_token,
                owner_user_id=owner_user_id,
                guild_id=guild_id,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.discord.connect",
            inputs={
                "token_supplied": bool(bot_token.strip()),
                "owner_supplied": bool(owner_user_id.strip()),
                "guild_supplied": bool(guild_id.strip()),
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/discord/test")
    def api_channels_discord_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_discord()
        _receipt(
            deps,
            tool="channels.discord.test",
            inputs={"channel": "discord"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/discord")
    def api_channels_discord_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_discord().to_json()
        _receipt(
            deps,
            tool="channels.discord.remove",
            inputs={"channel": "discord"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/slack")
    async def api_channels_slack_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            bot_token = str(body.get("bot_token") or "")
            owner_user_id = str(body.get("owner_user_id") or "")
            signing_secret = str(body.get("signing_secret") or "")
            status_json = deps.channels.connect_slack(
                bot_token=bot_token,
                owner_user_id=owner_user_id,
                signing_secret=signing_secret,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.slack.connect",
            inputs={
                "token_supplied": bool(bot_token.strip()),
                "owner_supplied": bool(owner_user_id.strip()),
                "signing_secret_supplied": bool(signing_secret.strip()),
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/slack/test")
    def api_channels_slack_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_slack()
        _receipt(
            deps,
            tool="channels.slack.test",
            inputs={"channel": "slack"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/slack")
    def api_channels_slack_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_slack().to_json()
        _receipt(
            deps,
            tool="channels.slack.remove",
            inputs={"channel": "slack"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/whatsapp")
    async def api_channels_whatsapp_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            access_token = str(body.get("access_token") or "")
            owner_phone = str(body.get("owner_phone") or "")
            phone_number_id = str(body.get("phone_number_id") or "")
            status_json = deps.channels.connect_whatsapp(
                access_token=access_token,
                owner_phone=owner_phone,
                phone_number_id=phone_number_id,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.whatsapp.connect",
            inputs={
                "access_token_supplied": bool(access_token.strip()),
                "owner_supplied": bool(owner_phone.strip()),
                "phone_number_id_supplied": bool(phone_number_id.strip()),
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/whatsapp/test")
    def api_channels_whatsapp_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_whatsapp()
        _receipt(
            deps,
            tool="channels.whatsapp.test",
            inputs={"channel": "whatsapp"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/whatsapp")
    def api_channels_whatsapp_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_whatsapp().to_json()
        _receipt(
            deps,
            tool="channels.whatsapp.remove",
            inputs={"channel": "whatsapp"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/email")
    async def api_channels_email_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            owner_email = str(body.get("owner_email") or "")
            smtp_host = str(body.get("smtp_host") or "")
            smtp_user = str(body.get("smtp_user") or "")
            smtp_pass = str(body.get("smtp_pass") or "")
            status_json = deps.channels.connect_email(
                owner_email=owner_email,
                smtp_host=smtp_host,
                smtp_user=smtp_user,
                smtp_pass=smtp_pass,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.email.connect",
            inputs={
                "owner_supplied": bool(owner_email.strip()),
                "smtp_host_supplied": bool(smtp_host.strip()),
                "smtp_user_supplied": bool(smtp_user.strip()),
                "smtp_pass_supplied": bool(smtp_pass.strip()),
                "mode": "draft_only",
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/email/test")
    def api_channels_email_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_email()
        _receipt(
            deps,
            tool="channels.email.test",
            inputs={"channel": "email", "mode": "draft_only"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/email")
    def api_channels_email_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_email().to_json()
        _receipt(
            deps,
            tool="channels.email.remove",
            inputs={"channel": "email"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/sms")
    async def api_channels_sms_connect(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            account_sid = str(body.get("account_sid") or "")
            auth_token = str(body.get("auth_token") or "")
            from_number = str(body.get("from_number") or "")
            owner_phone = str(body.get("owner_phone") or "")
            status_json = deps.channels.connect_sms(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                owner_phone=owner_phone,
            ).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="channels.sms.connect",
            inputs={
                "account_sid_supplied": bool(account_sid.strip()),
                "auth_token_supplied": bool(auth_token.strip()),
                "from_number_supplied": bool(from_number.strip()),
                "owner_supplied": bool(owner_phone.strip()),
            },
            outputs={"connected": status_json["connected"], "missing": status_json["missing"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.post("/api/channels/sms/test")
    def api_channels_sms_test(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        result = deps.channels.test_sms()
        _receipt(
            deps,
            tool="channels.sms.test",
            inputs={"channel": "sms"},
            outputs={"ok": result["ok"], "missing": result["missing"]},
            decision=Decision.ALLOW if result["ok"] else Decision.DENY,
        )
        return _json(200, result)

    @app.delete("/api/channels/sms")
    def api_channels_sms_remove(request: Request) -> Response:
        _require_session(request)
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        status_json = deps.channels.remove_sms().to_json()
        _receipt(
            deps,
            tool="channels.sms.remove",
            inputs={"channel": "sms"},
            outputs={"connected": status_json["connected"]},
        )
        return _json(200, {"ok": True, "channel": status_json})

    @app.get("/api/providers")
    def api_providers(request: Request) -> Response:
        _require_session(request)
        if deps.providers is None:
            return _json(503, {"error": "providers disabled"})
        return _json(200, {"providers": deps.providers.list_statuses()})

    @app.post("/api/providers")
    async def api_provider_add(request: Request) -> Response:
        _require_session(request)
        if deps.providers is None:
            return _json(503, {"error": "providers disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            provider = str(body.get("provider") or "")
            api_key = _optional_secret(body.get("api_key"))
            base_url = _optional_secret(body.get("base_url"))
            status_json = deps.providers.add(provider, api_key=api_key, base_url=base_url)
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="providers.add",
            inputs={
                "provider": status_json["name"],
                "api_key_supplied": bool(api_key),
                "base_url_supplied": bool(base_url),
            },
            outputs={
                "configured": status_json["configured"],
                "missing": status_json["missing"],
            },
        )
        return _json(200, {"ok": True, "provider": status_json})

    @app.post("/api/providers/test")
    async def api_provider_test(request: Request) -> Response:
        _require_session(request)
        if deps.providers is None:
            return _json(503, {"error": "providers disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            result = deps.providers.test(
                str(body.get("provider") or ""),
                live=bool(body.get("live") or False),
                model=str(body["model"]) if body.get("model") else None,
                router=deps.router,
            )
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="providers.test",
            inputs={"provider": result.provider, "live": result.live, "model": result.model},
            outputs={"ok": result.ok, "message_len": len(result.message)},
            decision=Decision.ALLOW if result.ok else Decision.DENY,
            cost_usd=result.cost_usd,
        )
        return _json(200, result.to_json())

    @app.delete("/api/providers/{provider}")
    def api_provider_remove(request: Request, provider: str) -> Response:
        _require_session(request)
        if deps.providers is None:
            return _json(503, {"error": "providers disabled"})
        try:
            status_json = deps.providers.remove(provider)
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="providers.remove",
            inputs={"provider": status_json["name"]},
            outputs={"configured": status_json["configured"]},
        )
        return _json(200, {"ok": True, "provider": status_json})

    @app.get("/api/settings")
    def api_settings_get(request: Request) -> Response:
        _require_session(request)
        if deps.settings_store is None:
            return _json(503, {"error": "settings disabled"})
        return _json(200, {"settings": deps.settings_store.get().to_json()})

    @app.post("/api/settings")
    async def api_settings_post(request: Request) -> Response:
        _require_session(request)
        if deps.settings_store is None:
            return _json(503, {"error": "settings disabled"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            settings_json = deps.settings_store.update(body).to_json()
        except (TypeError, ValueError) as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="settings.update",
            inputs={"fields": sorted(body.keys())},
            outputs=settings_json,
        )
        return _json(200, {"ok": True, "settings": settings_json})

    @app.post("/api/chat")
    async def api_chat(request: Request) -> Any:
        _require_session(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            message = str(body.get("message") or "").strip()
            history = body.get("history") if isinstance(body.get("history"), list) else []
            mode = str(body.get("mode") or "chat").strip().lower()
            if mode not in {"chat", "do"}:
                return _json(400, {"error": "mode must be 'chat' or 'do'"})
            if not message:
                return _json(400, {"error": "message required"})
        except Exception:
            return _json(400, {"error": "invalid json"})

        from starlette.responses import StreamingResponse

        run_id = f"{mode}:{uuid.uuid4().hex[:12]}"

        if mode == "do":
            if deps.sentinel is None or deps.fs_guard is None:
                return _json(503, {"error": "executor disabled"})
            return StreamingResponse(
                _do_mode_stream(deps, message, run_id),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
            )

        if deps.router is None or deps.sentinel is None:
            return _json(503, {"error": "chat disabled"})

        async def gen():
            yield _sse("start", {"run_id": run_id})
            try:
                bundle = run_chat(
                    message=message,
                    history=history,
                    router=deps.router,
                    sentinel=deps.sentinel,
                    approvals=deps.queue,
                    ledger=deps.ledger,
                    run_id=run_id,
                    est_usd=deps.chat_est_usd,
                )
            except BudgetExceeded as exc:
                yield _sse(
                    "error",
                    {
                        "code": "budget_exceeded",
                        "scope": exc.scope,
                        "projected": round(exc.projected, 6),
                        "cap": round(exc.cap, 6),
                    },
                )
                return
            except Exception:
                yield _sse("error", {"code": "chat_failed"})
                return

            for chunk in _text_chunks(bundle.text):
                yield _sse("delta", {"text": chunk})
            if bundle.approval is not None:
                yield _sse("approval", bundle.approval.to_json())
            yield _sse(
                "done",
                {
                    "run_id": bundle.run_id,
                    "proof_level": bundle.proof_level,
                    "sources": bundle.sources,
                    "cost_usd": round(bundle.cost_usd, 6),
                },
            )

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @app.get("/api/artifacts")
    def api_artifacts(request: Request) -> Response:
        """List every artifact materialized by `execute_approved_step`.

        Walks the ledger for `*.executed` tool receipts. Each entry surfaces the
        artifact's path, sha256, and `run_id` so the SPA can link back to the
        Proof Ledger for the full chain.
        """
        _require_session(request)
        if deps.ledger is None:
            return _json(200, {"artifacts": []})
        executed: list[dict[str, Any]] = []
        for receipt in deps.ledger:
            tool = receipt.body.tool
            if not tool.endswith(".executed"):
                continue
            executed.append(
                {
                    "seq": receipt.body.seq,
                    "run_id": receipt.body.run_id,
                    "kind": tool.removesuffix(".executed"),
                    "ts": receipt.body.ts,
                    "hash": receipt.hash,
                }
            )
        return _json(200, {"artifacts": list(reversed(executed))[:100]})

    @app.post("/api/execute/{approval_id}")
    async def api_execute(request: Request, approval_id: int) -> Response:
        """Materialize an APPROVED gated step. Returns the executed receipt summary."""
        _require_session(request)
        from midas.core.approvals.queue import ApprovalStatus

        if deps.ledger is None or deps.fs_guard is None:
            return _json(503, {"error": "executor not available"})
        req = deps.queue.get(approval_id)
        if req is None:
            return _json(404, {"error": "unknown approval"})
        if req.status != ApprovalStatus.APPROVED:
            return _json(
                409,
                {"error": f"approval is {req.status.value}, must be approved"},
            )
        from midas.flagship.agent.execute import execute_approved_step

        try:
            result = execute_approved_step(_dashboard_runtime_shim(deps), req)
        except KeyError:
            return _json(400, {"error": "no executor for this tool"})
        except (ValueError, PermissionError) as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, {"ok": True, "result": result})

    @app.get("/events")
    async def events(request: Request) -> Any:
        # Owner-gated SSE. The stream is no-cache and Content-Type text/event-stream,
        # set explicitly so middleware overrides don't break the wire format.
        _require_session(request)
        from starlette.responses import StreamingResponse

        async def gen():
            async for frame in event_stream(
                queue=deps.queue, ledger=deps.ledger,
                interval_seconds=deps.sse_interval_seconds,
            ):
                if await request.is_disconnected():
                    return
                yield frame

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @app.get("/snapshot")
    def snapshot(request: Request) -> Response:
        # Fallback for tests + EventSource-less clients. Same data as one SSE tick.
        _require_session(request)
        s = take_snapshot(queue=deps.queue, ledger=deps.ledger)
        return _json(200, {
            "spent_usd": round(s.spent_usd, 6),
            "receipts": s.receipt_count,
            "pending": s.pending_count,
        })

    @app.post("/outcomes")
    async def outcomes(request: Request) -> Response:
        _require_session(request)
        if deps.memory is None:
            return _json(503, {"error": "outcomes disabled (no memory configured)"})
        try:
            body = await request.json()
        except Exception:
            return _json(400, {"error": "invalid json"})

        # Strict shape — never `eval` user input; reject unknown fields by ignoring them.
        try:
            outcome = Outcome(
                move_key=str(body["move_key"]),
                outcome=str(body["outcome"]),
                metrics={str(k): float(v) for k, v in (body.get("metrics") or {}).items()},
                sources=[str(s) for s in (body.get("sources") or [])],
                note=str(body.get("note") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return _json(400, {"error": f"bad outcome: {exc}"})

        entry = ingest_outcome(outcome, memory=deps.memory, ledger=deps.ledger)
        return _json(200, {
            "ok": True,
            "id": entry.id,
            "proof_level": entry.proof_level.value,
        })

    @app.post("/api/outcomes")
    async def api_outcomes(request: Request) -> Response:
        return await outcomes(request)

    @app.get("/api/export")
    def api_export(request: Request) -> Response:
        _require_session(request)
        from dataclasses import asdict

        from midas.core.memory import MemoryKind

        manifest: dict[str, Any] = {
            "version": 1,
            "exported_ts": _utcnow(),
            "memory": [],
            "competitors": [],
            "schedules": [],
            "skills": [],
        }
        if deps.memory is not None:
            entries: list[dict[str, Any]] = []
            for k in MemoryKind:
                entries.extend(
                    _memory_history_json(row)
                    for row in deps.memory.recall(
                        kind=k, include_superseded=True, limit=10_000
                    )
                )
            manifest["memory"] = entries
        if deps.competitors is not None:
            manifest["competitors"] = [
                c.__dict__ for c in deps.competitors.list()
            ]
        if deps.schedule_store is not None:
            manifest["schedules"] = [asdict(r) for r in deps.schedule_store.list()]
        if deps.skill_registry is not None:
            manifest["skills"] = [asdict(m) for m in deps.skill_registry.list()]
        _receipt(
            deps,
            tool="export",
            inputs={"kinds": ["memory", "competitors", "schedules", "skills"]},
            outputs={"memory_count": len(manifest["memory"])},
        )
        return _json(200, manifest)

    @app.post("/api/import")
    async def api_import(request: Request) -> Response:
        _require_session(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
        except Exception:
            return _json(400, {"error": "invalid json"})
        if int(body.get("version") or 0) != 1:
            return _json(400, {"error": "unsupported manifest version"})

        # Imports are approval-gated: queue the manifest summary and let the operator
        # approve from the Approvals page before any data is restored.
        memory_count = len(body.get("memory") or [])
        competitors_count = len(body.get("competitors") or [])
        schedules_count = len(body.get("schedules") or [])
        skills_count = len(body.get("skills") or [])
        req = deps.queue.enqueue(
            run_id="dashboard:import",
            agent="dashboard",
            tool="data.import",
            action="restore_backup",
            summary=(
                f"Restore backup: {memory_count} memory · {competitors_count} competitors · "
                f"{schedules_count} schedules · {skills_count} skills"
            ),
            payload={
                "memory_count": memory_count,
                "competitors_count": competitors_count,
                "schedules_count": schedules_count,
                "skills_count": skills_count,
                "exported_ts": body.get("exported_ts"),
            },
        )
        _receipt(
            deps,
            tool="data.import",
            inputs={"manifest_version": 1},
            outputs={"approval_id": req.id},
            decision=Decision.QUEUE_APPROVAL,
        )
        return _json(200, {"ok": True, "approval_id": req.id})

    @app.post("/api/council")
    async def api_council(request: Request) -> Response:
        _require_session(request)
        if deps.router is None:
            return _json(
                503,
                {"error": "router not configured — set providers to use the council"},
            )
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            question = str(body.get("question") or "").strip()
        except Exception:
            return _json(400, {"error": "invalid json"})
        if not question:
            return _json(400, {"error": "question required"})

        from midas.core.router.council import Council

        members_cfg = list(getattr(deps.router.providers, "council", []) or [])
        chairman_cfg = (
            getattr(deps.router.providers, "chairman", None) or members_cfg[0:1]
        )
        if not members_cfg or not chairman_cfg:
            return _json(
                400,
                {"error": "council/chairman models not configured in providers"},
            )
        chairman = (
            chairman_cfg[0] if isinstance(chairman_cfg, list) else chairman_cfg
        )
        council = Council(deps.router, members_cfg, chairman)
        try:
            result = council.deliberate(
                [{"role": "user", "content": question}],
                run_id="dashboard:council",
                est_usd_each=0.01,
            )
        except Exception as exc:  # noqa: BLE001 — surface to UI, never crash dashboard
            return _json(500, {"error": f"council failed: {exc.__class__.__name__}"})
        return _json(
            200,
            {
                "agreement": round(result.agreement, 4),
                "escalate_to_human": result.escalate_to_human,
                "answers": [a.text for a in result.answers],
                "final": result.final.text,
            },
        )

    @app.get("/api/skills")
    def api_skills_list(request: Request) -> Response:
        _require_session(request)
        if deps.skill_registry is None:
            return _json(200, {"skills": []})
        from dataclasses import asdict

        return _json(
            200, {"skills": [asdict(m) for m in deps.skill_registry.list()]}
        )

    @app.post("/api/skills")
    async def api_skills_create(request: Request) -> Response:
        _require_session(request)
        if deps.skill_registry is None:
            return _json(503, {"error": "skill registry not configured"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            name = str(body.get("name") or "").strip()
            summary = str(body.get("summary") or "").strip()
            perms_in = body.get("permissions") or ["read"]
            if not isinstance(perms_in, list):
                return _json(400, {"error": "permissions must be a list"})
            permissions = [str(p).strip() for p in perms_in if str(p).strip()]
        except Exception:
            return _json(400, {"error": "invalid json"})
        if not name or not summary:
            return _json(400, {"error": "name and summary required"})
        try:
            manifest = deps.skill_registry.create(
                name=name, summary=summary, permissions=permissions
            )
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="skills.create",
            inputs={"name": name},
            outputs={"sha256": manifest.sha256},
        )
        from dataclasses import asdict as _asdict

        return _json(200, {"ok": True, "skill": _asdict(manifest)})

    @app.delete("/api/skills/{name}")
    def api_skills_delete(request: Request, name: str) -> Response:
        _require_session(request)
        if deps.skill_registry is None:
            return _json(503, {"error": "skill registry not configured"})
        import json as _json_mod
        import shutil
        from dataclasses import asdict

        registry = deps.skill_registry
        target = registry.skills_dir / name
        rows = [m for m in registry.list() if m.name != name]
        if len(rows) == len(registry.list()):
            return _json(404, {"error": "skill not found"})
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        registry.index_path.write_text(
            _json_mod.dumps([asdict(m) for m in rows], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _receipt(
            deps,
            tool="skills.delete",
            inputs={"name": name},
            outputs={"removed": True},
        )
        return _json(200, {"ok": True})

    @app.post("/api/skills/plan-download")
    async def api_skills_plan_download(request: Request) -> Response:
        _require_session(request)
        if deps.skill_registry is None:
            return _json(503, {"error": "skill registry not configured"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            url = str(body.get("url") or "").strip()
            reason = str(body.get("reason") or "").strip()
        except Exception:
            return _json(400, {"error": "invalid json"})
        from midas.flagship.skills import is_remote_skill_source

        if not url:
            return _json(400, {"error": "url required"})
        if not is_remote_skill_source(url):
            return _json(400, {"error": "url is not a remote skill source"})
        req = deps.queue.enqueue(
            run_id="dashboard:skills",
            agent="dashboard",
            tool="skills.plan_download",
            action="download_remote_skill",
            summary=f"Download remote skill from {url}",
            payload={"url": url, "reason": reason or "operator-initiated"},
        )
        _receipt(
            deps,
            tool="skills.plan_download",
            inputs={"url": url},
            outputs={"approval_id": req.id},
            decision=Decision.QUEUE_APPROVAL,
        )
        return _json(200, {"ok": True, "approval_id": req.id})

    @app.post("/api/research")
    async def api_research(request: Request) -> Response:
        _require_session(request)
        if deps.search is None or deps.fetcher is None:
            return _json(503, {"error": "research requires search + fetcher"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            question = str(body.get("question") or "").strip()
            k = int(body.get("k") or 5)
        except Exception:
            return _json(400, {"error": "invalid json"})
        if not question:
            return _json(400, {"error": "question required"})

        from midas.core.web import research as run_research

        result = run_research(
            question, search=deps.search, fetcher=deps.fetcher, verifier=deps.verifier, k=k
        )
        _receipt(
            deps,
            tool="research.run",
            inputs={"question": question, "k": k},
            outputs={
                "verified": result.verified_count,
                "proof_level": result.proof_level.value,
                "sources": [s.url for s in result.sources],
            },
        )
        return _json(200, {"result": result.as_dict()})

    def _autoskills_store() -> Any:
        if deps.skill_registry is None or deps.ledger is None:
            return None
        from midas.flagship.autoskills import AutoSkills, AutoSkillsStore

        state_dir = deps.skill_registry.root
        store = AutoSkillsStore(state_dir / "autoskills.json")
        return AutoSkills(
            registry=deps.skill_registry,
            ledger=deps.ledger,
            queue=deps.queue,
            store=store,
            search=deps.search,
        )

    @app.get("/api/autoskills")
    def api_autoskills_list(request: Request) -> Response:
        _require_session(request)
        auto = _autoskills_store()
        if auto is None:
            return _json(503, {"error": "auto-skills requires skill registry + ledger"})
        auto.detect()
        proposals = [
            {
                "proposal_id": p.proposal_id,
                "run_id": p.run_id,
                "name": p.name,
                "summary": p.summary,
                "local_only": p.local_only,
                "status": p.status,
                "steps": p.steps,
                "skill_name": p.skill_name,
            }
            for p in auto._store.pending()  # noqa: SLF001
        ]
        return _json(200, {"proposals": proposals})

    @app.post("/api/autoskills/{proposal_id}/accept")
    def api_autoskills_accept(request: Request, proposal_id: str) -> Response:
        _require_session(request)
        auto = _autoskills_store()
        if auto is None:
            return _json(503, {"error": "auto-skills not available"})
        try:
            manifest = auto.accept(proposal_id)
        except KeyError:
            return _json(404, {"error": "unknown proposal"})
        except PermissionError as exc:
            return _json(403, {"error": str(exc)})
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, {"ok": True, "skill": {"name": manifest.name, "sha256": manifest.sha256}})

    @app.post("/api/autoskills/{proposal_id}/discard")
    async def api_autoskills_discard(request: Request, proposal_id: str) -> Response:
        _require_session(request)
        auto = _autoskills_store()
        if auto is None:
            return _json(503, {"error": "auto-skills not available"})
        try:
            body = await request.json() if request.headers.get("content-length") else {}
            reason = str((body or {}).get("reason") or "")
        except Exception:
            reason = ""
        try:
            auto.discard(proposal_id, reason=reason)
        except KeyError:
            return _json(404, {"error": "unknown proposal"})
        return _json(200, {"ok": True})

    @app.post("/api/multimodal/inspect")
    async def api_multimodal_inspect(request: Request) -> Response:
        _require_session(request)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            path = str(body.get("path") or "").strip()
        except Exception:
            return _json(400, {"error": "invalid json"})
        if not path:
            return _json(400, {"error": "path required"})
        from midas.flagship.multimodal import inspect_media

        try:
            result = inspect_media(path)
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        _receipt(
            deps,
            tool="multimodal.inspect",
            inputs={"path": path},
            outputs={
                "kind": result.kind,
                "sha256": result.sha256,
                "size_bytes": result.size_bytes,
            },
        )
        return _json(200, {"ok": True, "media": result.as_dict()})

    @app.get("/api/schedules")
    def api_schedules_list(request: Request) -> Response:
        _require_session(request)
        if deps.schedule_store is None:
            return _json(200, {"schedules": []})
        from dataclasses import asdict

        return _json(
            200, {"schedules": [asdict(r) for r in deps.schedule_store.list()]}
        )

    @app.post("/api/schedules")
    async def api_schedules_add(request: Request) -> Response:
        _require_session(request)
        if deps.schedule_store is None:
            return _json(503, {"error": "schedule store not configured"})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return _json(400, {"error": "json object required"})
            name = str(body.get("name") or "").strip()
            niche = str(body.get("niche") or "").strip()
            at = str(body.get("at") or "09:00").strip()
            mode = str(body.get("mode") or "deep").strip()
            base_dir = str(body.get("base_dir") or ".").strip()
        except Exception:
            return _json(400, {"error": "invalid json"})
        if not name or not niche:
            return _json(400, {"error": "name and niche required"})
        if mode not in {"fast", "deep", "war-room"}:
            return _json(400, {"error": "invalid mode"})
        from midas.flagship.schedule import daily_scan_recipe

        try:
            recipe = daily_scan_recipe(
                name=name, niche=niche, at=at, base_dir=base_dir, mode=mode
            )
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        deps.schedule_store.add(recipe)
        _receipt(
            deps,
            tool="schedule.add",
            inputs={"name": name, "niche": niche, "at": at, "mode": mode},
            outputs={"cadence": recipe.cadence},
        )
        from dataclasses import asdict as _asdict

        return _json(200, {"ok": True, "recipe": _asdict(recipe)})

    @app.delete("/api/schedules/{name}")
    def api_schedules_delete(request: Request, name: str) -> Response:
        _require_session(request)
        if deps.schedule_store is None:
            return _json(503, {"error": "schedule store not configured"})
        existing = [r for r in deps.schedule_store.list() if r.name == name]
        if not existing:
            return _json(404, {"error": "schedule not found"})
        # ScheduleStore overwrites the whole list — write back without the deleted one.
        import json as _json_mod
        from dataclasses import asdict

        remaining = [r for r in deps.schedule_store.list() if r.name != name]
        deps.schedule_store.path.write_text(
            _json_mod.dumps(
                [asdict(r) for r in remaining], indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        _receipt(
            deps,
            tool="schedule.delete",
            inputs={"name": name},
            outputs={"removed": True},
        )
        return _json(200, {"ok": True})

    @app.post("/api/webhooks/stripe")
    async def api_webhooks_stripe(request: Request) -> Response:
        """Stripe webhook receiver — verifies HMAC, auto-records cash.

        This is the ONE unauthenticated endpoint in the dashboard. Stripe calls
        it from the public internet (after the operator exposes loopback via
        ngrok/cloudflared). We always return 200 on verified events to avoid
        noisy Stripe retries; signature failures get 400. Body parsing happens
        only AFTER the signature is verified.
        """
        import os

        from midas.flagship.stripe_webhook import (
            StripeWebhookError,
            parse_event,
            record_cash_from_event,
            verify_signature,
        )

        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        signature = request.headers.get("stripe-signature", "")
        body = await request.body()
        try:
            verify_signature(payload=body, signature_header=signature, secret=secret)
        except StripeWebhookError as e:
            # Signature failure is the ONE case where we want a non-2xx — it
            # tells Stripe (and operations) that something is wrong upstream.
            return _json(400, {"error": str(e)})
        try:
            event = parse_event(body)
        except StripeWebhookError as e:
            # Parsed body is malformed → still 400 (the operator's config sent
            # garbage; we don't want infinite retries on it).
            return _json(400, {"error": str(e)})
        recorded = record_cash_from_event(deps.memory, event)
        return _json(
            200,
            {
                "ok": True,
                "event_id": event.id,
                "event_type": event.type,
                "recorded": recorded,
            },
        )

    @app.get("/api/outcomes/history")
    def api_outcomes_history(request: Request, move_key: str = "") -> Response:
        _require_session(request)
        if deps.memory is None:
            return _json(503, {"error": "memory disabled"})
        from midas.core.memory import MemoryKind
        from midas.flagship.outcomes import summarize_history

        move_key = move_key.strip()
        if move_key:
            summary = summarize_history(deps.memory, move_key)
            entries = [
                _memory_history_json(r)
                for r in deps.memory.history(MemoryKind.RESULT, move_key)
                if not r.superseded
            ]
            return _json(200, {"summary": summary, "entries": entries})
        # Otherwise list all live RESULT memories, newest first.
        rows = deps.memory.recall(kind=MemoryKind.RESULT, limit=50)
        return _json(200, {"entries": [_memory_history_json(r) for r in rows]})

    # SPA catch-all — must stay LAST so every concrete route above wins first. Serves
    # the React shell for any client-side route React Router owns. Session-required.
    @app.get("/{spa_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def spa_catchall(request: Request, spa_path: str) -> Any:
        if spa_path.startswith(_NON_SPA_PREFIXES) or not _spa_available():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        _require_session(request)
        return HTMLResponse(_SPA_INDEX.read_text(encoding="utf-8"))

    return app


async def _do_mode_stream(deps: DashboardDeps, task: str, run_id: str) -> Any:
    """Stream AgentLoop steps as SSE for the Chat page's Do mode.

    Yields one ``step`` event per AgentStep (tool, decision, ran, approval_id,
    output_summary) and one ``done`` event at the end of the run, plus an
    ``approval`` event mirroring any queued ApprovalRequest so the existing
    Chat UI's approval pane can pick them up.
    """
    from midas.core.budget.fuse import BudgetExceeded as _BudgetExceeded
    from midas.flagship.agent import AgentLoop, build_default_toolset

    yield _sse("start", {"run_id": run_id, "mode": "do"})

    if deps.fs_guard is None or deps.sentinel is None:
        yield _sse("error", {"code": "executor_unavailable"})
        return

    try:
        toolset = build_default_toolset(
            sentinel=deps.sentinel,
            guard=deps.fs_guard,
            ledger=deps.ledger,
            approvals=deps.queue,
            run_id=run_id,
            search=deps.search,
            fetcher=deps.fetcher,
            verifier=deps.verifier,
        )
        from midas.flagship.agent.loop import llm_planner

        loop = AgentLoop(
            toolset=toolset,
            planner=(
                llm_planner(deps.router, memory=deps.memory)
                if deps.router is not None
                else _refuse_planner
            ),
            max_steps=6,
            agent_name="dashboard-do",
        )
    except Exception:
        yield _sse("error", {"code": "executor_init_failed"})
        return

    try:
        transcript = loop.run(task)
    except _BudgetExceeded as exc:
        yield _sse(
            "error",
            {
                "code": "budget_exceeded",
                "scope": exc.scope,
                "projected": round(exc.projected, 6),
                "cap": round(exc.cap, 6),
            },
        )
        return
    except Exception:
        yield _sse("error", {"code": "do_failed"})
        return

    for step in transcript.steps:
        yield _sse(
            "step",
            {
                "tool": step.tool,
                "decision": step.decision,
                "ran": step.ran,
                "approval_id": step.approval_id,
                "output_summary": step.output_summary,
                "error": step.error,
            },
        )
        if step.approval_id is not None:
            req = deps.queue.get(step.approval_id)
            if req is not None:
                yield _sse("approval", _approval_json(req))

    yield _sse(
        "done",
        {
            "run_id": run_id,
            "stopped_reason": transcript.stopped_reason,
            "step_count": len(transcript.steps),
            "queued_approvals": transcript.queued_approvals,
        },
    )


def _refuse_planner(task: str, transcript: Any) -> dict[str, Any]:
    """Fallback planner when no LLM is configured — reuses the offline planner."""
    from midas.flagship.agent.loop import offline_artifact_planner

    return offline_artifact_planner(task, transcript)


class _RuntimeShim:
    """Minimal runtime-shaped object for ``execute_approved_step`` from the dashboard."""

    def __init__(self, deps: DashboardDeps) -> None:
        self.ledger = deps.ledger
        self.approvals = deps.queue
        self.fs_guard = deps.fs_guard

    def append_receipt(
        self,
        *,
        run_id: str,
        agent: str,
        tool: str,
        inputs: Any,
        outputs: Any,
        decision: Any = None,
        cost_usd: float = 0.0,
    ) -> None:
        if self.ledger is None:
            return
        from midas.core.receipts.models import Decision

        self.ledger.append(
            run_id=run_id,
            agent=agent,
            tool=tool,
            decision=decision or Decision.ALLOW,
            inputs=inputs,
            outputs=outputs,
            cost_usd=cost_usd,
        )


def _dashboard_runtime_shim(deps: DashboardDeps) -> Any:
    return _RuntimeShim(deps)


def _resolve(deps: DashboardDeps, req_id: int, *, approve: bool) -> Response:
    try:
        # Same queue used by every other channel — single source of truth.
        if approve:
            deps.queue.approve(req_id, by="dashboard")
        else:
            deps.queue.reject(req_id, by="dashboard")
    except ApprovalError as exc:
        # 409 = state conflict (already resolved). Idempotency surfaces cleanly.
        return _json(409, {"error": str(exc)})
    return _json(200, {"ok": True, "id": req_id})


_CAPABILITY_GROUPS: dict[str, str] = {
    "fs.": "Files",
    "pdf.": "Files",
    "sheet.": "Files",
    "csv.": "Files",
    "json.": "Files",
    "artifact.": "Cash artifacts",
    "landing.": "Cash artifacts",
    "product.": "Cash artifacts",
    "outreach.": "Cash artifacts",
    "proposal.": "Cash artifacts",
    "quote.": "Cash artifacts",
    "adcopy.": "Cash artifacts",
    "email.draft": "Cash artifacts",
    "email.inbox.": "Inbound",
    "email.": "Cash artifacts",
    "invoice.": "Cash artifacts",
    "voice.": "Cash artifacts",
    "image.": "Cash artifacts",
    "social.": "Social",
    "stripe.": "Cash collection",
    "affiliate.": "Cash collection",
    "research.": "Research",
    "web.": "Research",
    "http.": "Research",
    "mcp.": "External tools (MCP)",
    "code.": "Code",
    "skill.": "Skills",
}


def _capability_group(name: str) -> str:
    for prefix, group in _CAPABILITY_GROUPS.items():
        if name.startswith(prefix):
            return group
    return "Other"


def _approval_json(req: Any) -> dict[str, Any]:
    return {
        "id": req.id,
        "run_id": req.run_id,
        "agent": req.agent,
        "tool": req.tool,
        "action": req.action,
        "summary": req.summary,
        "payload": req.payload,
        "status": req.status.value,
        "created_ts": req.created_ts,
        "resolved_ts": req.resolved_ts,
        "resolver": req.resolver,
        "note": req.note,
    }


def _utcnow() -> str:
    from midas.core.receipts.models import utcnow_iso

    return utcnow_iso()


def _memory_json(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts,
        "kind": row.kind.value,
        "key": row.key,
        "content": row.content,
        "proof_level": row.proof_level.value,
        "sources": row.sources,
        "tags": row.tags,
    }


def _memory_history_json(row: Any) -> dict[str, Any]:
    payload = _memory_json(row)
    payload["superseded"] = bool(getattr(row, "superseded", False))
    return payload


def _snapshot_json(snap: Any) -> dict[str, Any]:
    return {
        "competitor_id": snap.competitor_id,
        "name": snap.name,
        "url": snap.url,
        "status": snap.status,
        "content_hash": snap.content_hash,
        "changed": snap.changed,
        "change_kind": snap.change_kind,
        "excerpt": snap.excerpt,
        "ts": snap.ts,
    }


def _resolve_fetcher(deps: DashboardDeps) -> Any:
    if deps.fetcher is not None:
        return deps.fetcher
    # Lazy-construct a stdlib-friendly HttpxFetcher so the dashboard is usable
    # even when the runtime didn't pre-wire a fetcher (tests inject their own).
    try:
        from midas.core.web.fetch import HttpxFetcher

        return HttpxFetcher()
    except Exception:
        return None


def _queue_move_approval(deps: DashboardDeps, report: Any, *, run_id: str) -> int | None:
    move = getattr(report, "daily_move", None)
    if move is None:
        return None
    req = deps.queue.enqueue(
        run_id=run_id,
        agent="midas",
        tool="business_asset",
        action="send_email",
        summary=f"Approve next action for {move.candidate.name}: {move.next_action}",
        payload={
            "candidate": move.candidate.name,
            "next_action": move.next_action,
            "asset_keys": sorted(move.brief.draft_assets),
        },
    )
    _receipt(
        deps,
        tool="approval.enqueue",
        inputs={"candidate": move.candidate.name},
        outputs={"approval_id": req.id},
        decision=Decision.QUEUE_APPROVAL,
    )
    return int(req.id)


def _scan_report_json(report: Any, run_id: str, approval_id: int | None) -> dict[str, Any]:
    move = getattr(report, "daily_move", None)
    return {
        "run_id": run_id,
        "niche": report.niche,
        "proof_level": report.proof_level.value,
        "spent_usd": report.spent_usd,
        "abstained_reason": report.abstained_reason,
        "approval_id": approval_id,
        "daily_move": None if move is None else _move_json(move),
        "shortlist": [_scored_json(item) for item in report.shortlist],
    }


def _move_json(move: Any) -> dict[str, Any]:
    candidate = move.candidate
    return {
        "name": candidate.name,
        "summary": candidate.summary,
        "score": round(float(move.breakdown.total), 4),
        "band": move.breakdown.band.value,
        "proof_level": move.proof_level.value,
        "sources": candidate.sources,
        "findings": [
            {
                "claim": finding.claim,
                "proof_level": finding.proof_level.value,
                "sources": finding.sources,
            }
            for finding in candidate.findings
        ],
        "steps": move.brief.steps,
        "assets": move.brief.draft_assets,
        "estimate": {
            "assumptions": move.estimate.assumptions,
            "est_cost_usd": move.estimate.est_cost_usd,
            "est_time_hours": move.estimate.est_time_hours,
            "note": move.estimate.note,
        },
        "next_action": move.next_action,
        "next_action_requires_approval": move.next_action_requires_approval,
    }


def _scored_json(item: Any) -> dict[str, Any]:
    return {
        "name": item.candidate.name,
        "summary": item.candidate.summary,
        "score": round(float(item.breakdown.total), 4),
        "band": item.band.value,
        "proof_level": item.candidate.proof_level.value,
        "weakest_factor": item.breakdown.weakest_factor,
        "sources": item.candidate.sources,
    }


def _candidate_from_topic(topic: str, summary: str) -> Any:
    from midas.core.agents.summary import Finding, ProofLevel
    from midas.flagship.opportunity import OpportunityCandidate
    from midas.flagship.scoring import FactorScores

    return OpportunityCandidate(
        name=topic,
        summary=summary,
        findings=[Finding(f"Operator-supplied asset request for {topic}.", ProofLevel.LOW)],
        factors=FactorScores(**{key: 7 for key in FactorScores.model_fields}),
    )


def _optional_secret(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _receipt(
    deps: DashboardDeps,
    *,
    tool: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    decision: Decision = Decision.ALLOW,
    cost_usd: float = 0.0,
) -> None:
    if deps.ledger is None:
        return
    deps.ledger.append(
        run_id="dashboard",
        agent="dashboard",
        tool=tool,
        decision=decision,
        inputs=inputs,
        outputs=outputs,
        cost_usd=cost_usd,
    )


def _sse(event: str, body: dict[str, Any]) -> str:
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _text_chunks(text: str, *, size: int = 160) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _json(code: int, body: dict) -> Response:
    return Response(
        content=json.dumps(body), status_code=code, media_type="application/json"
    )
