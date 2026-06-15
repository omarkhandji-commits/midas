"""Agent layer — the gated executor.

A small, deterministic agent loop drives `core.agents.Toolset.invoke()` for every
side-effecting step. Read tools run inline; mutating tools surface as approval cards.
Every verdict writes a signed receipt. Nothing executes a callable without passing
through Sentinel first.
"""

from .loop import AgentLoop, AgentStep, AgentTranscript
from .registry import build_default_toolset
from .tools.fsguard import FsGuard, FsGuardError

__all__ = [
    "AgentLoop",
    "AgentStep",
    "AgentTranscript",
    "build_default_toolset",
    "FsGuard",
    "FsGuardError",
]
