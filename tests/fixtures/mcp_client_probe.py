"""Probe the MIDAS MCP server as a real MCP client would (stdio)."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "midas.flagship.cli", "mcp", "serve"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) List tools (Claude Desktop does this on connection).
            tools = await session.list_tools()
            print(f"OK — MIDAS server exposes {len(tools.tools)} tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description[:70]}")

            # 2) Call a mutating tool — MUST return an approval ticket, not bytes.
            result = await session.call_tool(
                "landing_draft",
                {
                    "path": "from-mcp-client.html",
                    "headline": "Hello from Claude Desktop",
                    "cta_text": "Click",
                },
            )
            content = result.content[0].text if result.content else "(empty)"
            parsed = json.loads(content)
            assert parsed["status"] == "approval_queued", parsed
            assert parsed["approval_id"] is not None
            print(
                f"\nlanding_draft -> status={parsed['status']} "
                f"approval_id={parsed['approval_id']}"
            )

            # 3) Read-only view — must succeed inline.
            result = await session.call_tool("pipeline_view", {})
            content = result.content[0].text if result.content else "(empty)"
            pipeline = json.loads(content)
            print(f"\npipeline_view -> {len(pipeline)} row(s) (read-only OK)")


if __name__ == "__main__":
    asyncio.run(main())
