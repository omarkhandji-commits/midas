"""Minimal MCP server used as a test fixture.

Exposes two trivial tools so we can verify MIDAS connects, lists, calls — and
that every call goes through the gated path.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fake-fixture")


@mcp.tool()
def echo(text: str) -> str:
    """Echo a string back. Trivial."""
    return f"echoed: {text}"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run("stdio")
