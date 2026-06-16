"""MCP client — connect to external MCP servers and register their tools.

Security model. Every tool imported from an external MCP server is registered
under action ``call_external_mcp`` which lives in ``requires_approval`` of
``policy.yml`` (added by this WS). Its output is tagged ``Taint.UNTRUSTED`` so
the lethal-trifecta defense fires the moment a fetched MCP response would touch
private data with egress.

We do NOT auto-run subprocesses on startup. The client connects on demand: a
``list_tools()`` call spawns the server, queries it, and shuts down. Persistent
sessions are an explicit "midas mcp serve --persistent" choice (V2).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from midas.core.agents.toolset import Tool
from midas.core.receipts.models import Taint

from .config import McpServerConfig


@dataclass(frozen=True)
class McpToolSummary:
    """Description of one remote MCP tool (for listing / discovery)."""

    server: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified(self) -> str:
        return f"{self.server}/{self.name}"


@asynccontextmanager
async def _open(cfg: McpServerConfig):
    env = dict(os.environ)
    env.update(cfg.env or {})
    params = StdioServerParameters(command=cfg.command, args=list(cfg.args), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _list_tools(cfg: McpServerConfig) -> list[McpToolSummary]:
    summaries: list[McpToolSummary] = []
    async with _open(cfg) as session:
        result = await session.list_tools()
        for t in result.tools:
            summaries.append(
                McpToolSummary(
                    server=cfg.name,
                    name=t.name,
                    description=t.description or "",
                    input_schema=dict(t.inputSchema or {}),
                )
            )
    return summaries


def list_tools(cfg: McpServerConfig) -> list[McpToolSummary]:
    """List tools exposed by an external MCP server (one-shot subprocess)."""
    return asyncio.run(_list_tools(cfg))


async def _call(cfg: McpServerConfig, tool: str, arguments: dict[str, Any]) -> Any:
    async with _open(cfg) as session:
        result = await session.call_tool(tool, arguments)
        # FastMCP returns a list of content blocks; we collapse to text for simplicity.
        chunks = []
        for c in (result.content or []):
            text = getattr(c, "text", None)
            if text is not None:
                chunks.append(text)
        return "\n".join(chunks) if chunks else str(result)


def call_tool(cfg: McpServerConfig, tool: str, arguments: dict[str, Any]) -> Any:
    """Invoke a remote MCP tool (one-shot subprocess). UNTRUSTED output."""
    return asyncio.run(_call(cfg, tool, arguments))


def register_external_mcp_tools(
    toolset: Any,
    cfg: McpServerConfig,
    summaries: list[McpToolSummary] | None = None,
) -> list[str]:
    """Register every external MCP tool inside the existing ``Toolset``.

    - Each tool's action is ``call_external_mcp`` (APPROVE-tier per policy).
    - Output is tagged ``Taint.UNTRUSTED`` — third-party responses cannot be
      treated as instructions.
    - ``has_egress=True`` because the subprocess can talk to the network.
    - Tool name is ``mcp.<server-slug>.<remote_tool>`` so collisions are
      impossible and the receipt clearly says "this came from an MCP server".

    Returns the list of registered tool names.
    """
    if summaries is None:
        summaries = list_tools(cfg)
    prefix = cfg.tool_prefix()
    names: list[str] = []
    for s in summaries:
        local_name = f"{prefix}.{s.name}"

        def _fn(_cfg: McpServerConfig = cfg, _remote: str = s.name, **kwargs: Any) -> Any:
            return {"output": call_tool(_cfg, _remote, kwargs)}

        toolset.register(
            Tool(
                name=local_name,
                action="call_external_mcp",
                fn=_fn,
                output_taint=Taint.UNTRUSTED,
                has_egress=True,
                # Domain string is the server name; the egress allowlist for
                # policy can be set via the operator if they want to restrict.
                egress_domains=[f"mcp://{cfg.name}"],
            )
        )
        names.append(local_name)
    return names


__all__ = [
    "McpToolSummary",
    "list_tools",
    "call_tool",
    "register_external_mcp_tools",
]
