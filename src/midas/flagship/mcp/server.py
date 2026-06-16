"""MCP server — exposes MIDAS to Claude Desktop / Cursor / any MCP client.

Architecture. Each tool is a thin shim: it calls ``Toolset.invoke`` exactly the
same way the CLI / dashboard does. So an MCP client asking for ``landing.draft``
triggers the *same* code path → Sentinel → ApprovalQueue. The MCP response
returns the approval ticket (not the executed bytes), so an outside agent can
NEVER bypass approval.

Read-only views (pipeline, roi, replay listing) return synchronously since they
don't mutate anything.

Transport. Stdio by default (the universal MCP transport). Claude Desktop
launches MIDAS as a subprocess and talks JSON-RPC over its stdin/stdout.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP


def build_server(runtime: Any, *, name: str = "midas") -> FastMCP:
    """Build the MIDAS MCP server bound to a runtime.

    The runtime carries the ledger / approvals / sentinel — same as the CLI uses.
    """
    mcp = FastMCP(name)

    toolset = runtime.build_toolset(run_id="mcp:server")

    # ── mutating tools — every call queues an approval ───────────────────────

    @mcp.tool()
    def landing_draft(
        path: str, headline: str, cta_text: str,
        subheading: str = "", body: str = "", cta_href: str = "#",
    ) -> str:
        """Draft a landing page. APPROVAL REQUIRED before the file is written."""
        return _invoke_gated(
            toolset, "landing.draft",
            path=path, headline=headline, subheading=subheading,
            body=body, cta_text=cta_text, cta_href=cta_href,
        )

    @mcp.tool()
    def product_draft(
        path: str, title: str, deliverables: list[str],
        audience: str = "", problem: str = "", price_usd: float = 0.0,
    ) -> str:
        """Draft a digital product spec. APPROVAL REQUIRED."""
        return _invoke_gated(
            toolset, "product.draft",
            path=path, title=title, audience=audience, problem=problem,
            deliverables=deliverables, price_usd=price_usd,
        )

    @mcp.tool()
    def outreach_sequence(
        path: str, audience: str, offer: str, steps: list[dict[str, str]]
    ) -> str:
        """Draft an outreach sequence. APPROVAL REQUIRED before any send."""
        return _invoke_gated(
            toolset, "outreach.sequence",
            path=path, audience=audience, offer=offer, steps=steps,
        )

    @mcp.tool()
    def proposal_draft(
        path: str, client: str, project: str, scope: list[str],
        price_usd: float, timeline: str = "", currency: str = "USD",
    ) -> str:
        """Draft a client proposal. APPROVAL REQUIRED."""
        return _invoke_gated(
            toolset, "proposal.draft",
            path=path, client=client, project=project, scope=scope,
            price_usd=price_usd, timeline=timeline, currency=currency,
        )

    @mcp.tool()
    def quote_draft(
        path: str, client: str,
        items: list[list[Any]],  # MCP serializes tuples as lists
        currency: str = "USD", quote_number: str = "", notes: str = "",
    ) -> str:
        """Draft a quote. APPROVAL REQUIRED."""
        normalized = [(str(e[0]), float(e[1]), float(e[2])) for e in items]
        return _invoke_gated(
            toolset, "quote.draft",
            path=path, client=client, items=normalized,
            currency=currency, quote_number=quote_number, notes=notes,
        )

    @mcp.tool()
    def adcopy_draft(
        path: str, product: str, audience: str, variants: list[dict[str, str]],
    ) -> str:
        """Draft ad copy variants. APPROVAL REQUIRED."""
        return _invoke_gated(
            toolset, "adcopy.draft",
            path=path, product=product, audience=audience, variants=variants,
        )

    # ── read-only views — no approval needed ─────────────────────────────────

    @mcp.tool()
    def pipeline_view() -> str:
        """Return MIDAS pipeline state as JSON."""
        from midas.flagship.flows.cash_loop import CashLoop

        loop = CashLoop(
            toolset=runtime.build_toolset(),
            memory=runtime.memory, ledger=runtime.ledger, approvals=runtime.approvals,
        )
        return json.dumps(loop.pipeline(), indent=2, ensure_ascii=False, default=str)

    @mcp.tool()
    def approvals_pending() -> str:
        """List pending approvals as JSON. Approvals are still resolved via CLI."""
        pending = []
        try:
            for req in runtime.approvals.pending():
                pending.append({
                    "id": req.id,
                    "tool": req.tool,
                    "action": req.action,
                    "summary": req.summary,
                    "run_id": req.run_id,
                })
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        return json.dumps(pending, indent=2, default=str)

    @mcp.tool()
    def roi_report() -> str:
        """Return the ROI report (cost from receipts, revenue from outcomes)."""
        from midas.flagship.roi import build_outcomes_index, compute_run_roi

        outcomes = build_outcomes_index(runtime.memory)
        receipts = list(runtime.ledger)
        report = compute_run_roi(receipts, outcomes)
        return json.dumps(
            {
                "total_cost_usd": report.total_cost,
                "total_revenue_usd": report.total_revenue,
                "net_usd": report.net_usd,
                "runs": [
                    {
                        "run_id": r.run_id,
                        "cost_usd": r.cost_usd,
                        "revenue_usd": r.revenue_usd,
                        "net_usd": r.net_usd,
                    } for r in report.runs
                ],
            },
            indent=2, default=str,
        )

    return mcp


def _invoke_gated(toolset: Any, tool_name: str, **kwargs: Any) -> str:
    """Run a tool through Toolset.invoke; return a JSON ticket the MCP caller sees."""
    try:
        outcome = toolset.invoke(tool_name, agent="mcp", **kwargs)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "tool": tool_name, "error": str(exc)})
    return json.dumps(
        {
            "status": (
                "approval_queued"
                if outcome.verdict.decision.value == "queue_approval"
                else outcome.verdict.decision.value
            ),
            "tool": tool_name,
            "approval_id": outcome.approval_id,
            "message": (
                "MIDAS queued an approval. Nothing was written. Resolve with: "
                f"`midas approvals approve {outcome.approval_id}` then "
                f"`midas execute {outcome.approval_id}`."
                if outcome.approval_id is not None
                else (outcome.verdict.reason or "")
            ),
        },
        indent=2,
    )


def run_stdio(runtime: Any, *, name: str = "midas") -> None:
    """Run the server over stdio — the universal MCP transport."""
    server = build_server(runtime, name=name)
    server.run("stdio")


__all__ = ["build_server", "run_stdio"]
