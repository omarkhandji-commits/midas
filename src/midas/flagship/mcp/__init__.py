"""MCP integration — server + client + approval gating.

MIDAS speaks MCP both ways:

- **Server**: expose every cash-shaped tool (landing.draft, product.draft,
  outreach.sequence, proposal.draft, quote.draft, adcopy.draft, plus earn /
  pipeline / roi reads) to MCP clients like Claude Desktop and Cursor. Every
  invocation still goes through ``Toolset.invoke → Sentinel → ApprovalQueue``,
  so the approval-default invariant survives across the MCP boundary.

- **Client**: connect to external MCP servers (filesystem, github, slack, …)
  and register their tools inside the same ``Toolset`` as APPROVE-tier actions
  with ``output_taint=Taint.UNTRUSTED``. The lethal-trifecta defense stays
  active on third-party data.
"""

from __future__ import annotations

from .config import McpServerConfig, McpServersFile, load_servers_file, save_servers_file

__all__ = [
    "McpServerConfig",
    "McpServersFile",
    "load_servers_file",
    "save_servers_file",
]
