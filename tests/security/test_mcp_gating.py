"""WS-MCP — Approval gating + UNTRUSTED contract for external MCP tools.

Hard contracts verified here:

1. An external MCP tool registered via ``register_external_mcp_tools`` queues
   an approval on every invocation. It never runs inline.
2. Its output_taint is UNTRUSTED — so if combined with private-access +
   egress in a subsequent step, the Sentinel fires the lethal-trifecta deny.
3. The MCP config persistence round-trips correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="optional MCP SDK not installed")

from midas.core.approvals.queue import ApprovalQueue
from midas.core.config.models import (
    ActionsPolicy,
    ApprovalPolicy,
    AuditPolicy,
    FilesystemPolicy,
    ModelsPolicy,
    PolicyConfig,
    SourcesPolicy,
    SpendCaps,
)
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Taint
from midas.core.sentinel import Sentinel
from midas.flagship.agent.registry import build_default_toolset
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.mcp.client import McpToolSummary, register_external_mcp_tools
from midas.flagship.mcp.config import (
    McpServerConfig,
    McpServersFile,
    load_servers_file,
    remove_server,
    save_servers_file,
    upsert_server,
)


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={
                "repo_write", "execute_code", "write_spreadsheet",
                "call_external_mcp",  # ← MCP gate
            },
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],  # empty → all egress goes via approval/queue
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


def _build(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    guard = FsGuard(workspace=workspace.resolve())
    sentinel = Sentinel(_policy())
    ledger = ReceiptLedger(state / "receipts.jsonl", Signer.from_hex_seed("ab" * 32))
    approvals = ApprovalQueue(state / "apv.db", ledger=ledger)
    toolset = build_default_toolset(
        sentinel=sentinel, guard=guard, ledger=ledger, approvals=approvals, run_id="mcp-t",
    )
    return toolset, approvals, state


# ── config persistence ──────────────────────────────────────────────────────


def test_mcp_config_roundtrip(tmp_path: Path) -> None:
    cfg = McpServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(tmp_path)],
        env={"FOO": "bar"},
        note="local fs",
    )
    save_servers_file(tmp_path, McpServersFile(servers=[cfg]))
    loaded = load_servers_file(tmp_path)
    assert len(loaded.servers) == 1
    assert loaded.servers[0].name == "filesystem"
    assert loaded.servers[0].env["FOO"] == "bar"


def test_mcp_upsert_and_remove(tmp_path: Path) -> None:
    cfg1 = McpServerConfig(name="srv1", command="cmd1")
    cfg2 = McpServerConfig(name="srv2", command="cmd2")
    upsert_server(tmp_path, cfg1)
    upsert_server(tmp_path, cfg2)
    assert {s.name for s in load_servers_file(tmp_path).servers} == {"srv1", "srv2"}
    # Upsert by same name replaces (no duplicate).
    upsert_server(tmp_path, McpServerConfig(name="srv1", command="updated"))
    loaded = load_servers_file(tmp_path)
    assert len(loaded.servers) == 2
    srv1 = next(s for s in loaded.servers if s.name == "srv1")
    assert srv1.command == "updated"
    remove_server(tmp_path, "srv1")
    assert {s.name for s in load_servers_file(tmp_path).servers} == {"srv2"}


def test_tool_prefix_is_url_safe() -> None:
    cfg = McpServerConfig(name="Some Weird Name! With Spaces", command="x")
    assert cfg.tool_prefix() == "mcp.some-weird-name-with-spaces"


# ── approval-gating contract ─────────────────────────────────────────────────


def test_external_mcp_tool_queues_approval_never_runs_inline(tmp_path: Path) -> None:
    """The CORE INVARIANT: external MCP tools cannot execute inline."""
    toolset, approvals, _ = _build(tmp_path)
    cfg = McpServerConfig(name="fakefs", command="never-launched", args=[])
    summaries = [
        McpToolSummary(server="fakefs", name="read_file", description="read"),
        McpToolSummary(server="fakefs", name="write_file", description="write"),
    ]
    names = register_external_mcp_tools(toolset, cfg, summaries=summaries)
    assert names == ["mcp.fakefs.read_file", "mcp.fakefs.write_file"]

    # Invoking ANY of them queues — never spawns the subprocess.
    outcome = toolset.invoke("mcp.fakefs.read_file", agent="test", path="/etc/passwd")
    assert outcome.ran is False
    assert outcome.approval_id is not None
    assert outcome.verdict.decision.value == "queue_approval"

    pending = approvals.pending()
    assert any(req.tool == "mcp.fakefs.read_file" for req in pending)


def test_external_mcp_tool_is_untrusted_by_taint(tmp_path: Path) -> None:
    """Output taint must be UNTRUSTED so the trifecta defense stays active."""
    toolset, _, _ = _build(tmp_path)
    cfg = McpServerConfig(name="fakefs", command="x")
    summaries = [McpToolSummary(server="fakefs", name="read_file", description="")]
    register_external_mcp_tools(toolset, cfg, summaries=summaries)
    # Inspect the registered Tool object via the toolset's internal dict.
    tool = toolset._tools["mcp.fakefs.read_file"]  # noqa: SLF001
    assert tool.output_taint == Taint.UNTRUSTED
    assert tool.has_egress is True
    assert tool.action == "call_external_mcp"


def test_external_mcp_tool_unknown_name_denies(tmp_path: Path) -> None:
    """An MCP tool we never registered must be denied (default-deny on unknown)."""
    from midas.core.agents.toolset import ToolDenied

    toolset, _, _ = _build(tmp_path)
    try:
        toolset.invoke("mcp.nonexistent.read", agent="test")
        raise AssertionError("expected ToolDenied")
    except ToolDenied:
        pass


def test_mcp_tool_unique_prefix_prevents_collision(tmp_path: Path) -> None:
    """Two MCP servers can both expose a tool called 'read' without colliding."""
    toolset, _, _ = _build(tmp_path)
    register_external_mcp_tools(
        toolset, McpServerConfig(name="srv-a", command="x"),
        summaries=[McpToolSummary(server="srv-a", name="read", description="")],
    )
    register_external_mcp_tools(
        toolset, McpServerConfig(name="srv-b", command="x"),
        summaries=[McpToolSummary(server="srv-b", name="read", description="")],
    )
    assert "mcp.srv-a.read" in toolset._tools  # noqa: SLF001
    assert "mcp.srv-b.read" in toolset._tools  # noqa: SLF001
