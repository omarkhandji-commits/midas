"""MCP server registry — persisted in `.midas/mcp_servers.yml`.

A single YAML file with the list of external MCP servers the operator approved
to connect to. Mirrors the format used by Claude Desktop's `mcp.json` (command
+ args + env) so configs port over.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class McpServerConfig:
    """One external MCP server entry."""

    name: str                                   # logical name (becomes tool prefix)
    command: str                                # executable: "npx", "uvx", "python", ...
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    note: str = ""

    def tool_prefix(self) -> str:
        """Tools imported from this server become ``mcp.<name>.<tool>``."""
        safe = "".join(c.lower() if c.isalnum() else "-" for c in self.name)
        while "--" in safe:
            safe = safe.replace("--", "-")
        return f"mcp.{safe.strip('-') or 'srv'}"


@dataclass
class McpServersFile:
    """Top-level file: list of servers."""

    servers: list[McpServerConfig] = field(default_factory=list)


def _default_path(state_dir: str | Path) -> Path:
    return Path(state_dir) / "mcp_servers.yml"


def load_servers_file(state_dir: str | Path) -> McpServersFile:
    p = _default_path(state_dir)
    if not p.exists():
        return McpServersFile()
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    servers_raw = raw.get("servers") or []
    servers = []
    for entry in servers_raw:
        if not isinstance(entry, dict):
            continue
        servers.append(
            McpServerConfig(
                name=str(entry.get("name") or ""),
                command=str(entry.get("command") or ""),
                args=[str(a) for a in (entry.get("args") or [])],
                env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
                enabled=bool(entry.get("enabled", True)),
                note=str(entry.get("note") or ""),
            )
        )
    return McpServersFile(servers=servers)


def save_servers_file(state_dir: str | Path, file: McpServersFile) -> Path:
    p = _default_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"servers": [asdict(s) for s in file.servers]}
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def upsert_server(state_dir: str | Path, server: McpServerConfig) -> McpServersFile:
    """Add or replace a server entry by name."""
    file = load_servers_file(state_dir)
    file.servers = [s for s in file.servers if s.name != server.name]
    file.servers.append(server)
    save_servers_file(state_dir, file)
    return file


def remove_server(state_dir: str | Path, name: str) -> McpServersFile:
    file = load_servers_file(state_dir)
    file.servers = [s for s in file.servers if s.name != name]
    save_servers_file(state_dir, file)
    return file


__all__ = [
    "McpServerConfig",
    "McpServersFile",
    "load_servers_file",
    "save_servers_file",
    "upsert_server",
    "remove_server",
]
