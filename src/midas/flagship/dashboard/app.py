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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from midas.core.approvals import ApprovalError, ApprovalQueue
from midas.core.receipts.models import Decision
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
    def login_form(request: Request) -> Any:
        return templates.TemplateResponse(
            request, "login.html", {"nonce": request.state.nonce}
        )

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
                {"run_id": r.body.run_id, "receipts": 0, "cost_usd": 0.0, "latest_ts": ""},
            )
            item["receipts"] += 1
            item["cost_usd"] = round(float(item["cost_usd"]) + r.body.cost_usd, 6)
            item["latest_ts"] = r.body.ts
        return _json(200, {"runs": list(runs.values())[-50:]})

    @app.get("/api/proofs")
    def api_proofs(request: Request) -> Response:
        _require_session(request)
        receipts = list(deps.ledger) if deps.ledger is not None else []
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
        return _json(200, {"proofs": proofs})

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

    @app.get("/api/assets")
    def api_assets(request: Request) -> Response:
        _require_session(request)
        from midas.flagship.assets import ASSET_KEYS

        return _json(200, {"asset_types": list(ASSET_KEYS)})

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

    # SPA catch-all — must stay LAST so every concrete route above wins first. Serves
    # the React shell for any client-side route React Router owns. Session-required.
    @app.get("/{spa_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def spa_catchall(request: Request, spa_path: str) -> Any:
        if spa_path.startswith(_NON_SPA_PREFIXES) or not _spa_available():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        _require_session(request)
        return HTMLResponse(_SPA_INDEX.read_text(encoding="utf-8"))

    return app


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


def _json(code: int, body: dict) -> Response:
    import json
    return Response(
        content=json.dumps(body), status_code=code, media_type="application/json"
    )
