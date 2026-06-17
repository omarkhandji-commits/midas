"""Skill loader on-demand — Claude Code's token-economy pattern, ported.

Why
---
Loading every skill body into every LLM call wastes 5–10× more tokens than
necessary. The fix is the same as Claude Code's: keep a cheap *index* in the
planner's context (one line per skill: name + 1-sentence summary), and let
the planner pull a specific skill body via :func:`skill_load` only when one
matches the task at hand.

Both tools are AUTO-tier (``read_local_files``): they only read manifests
and Markdown bodies from ``~/.midas/skills/``. They never egress, never
mutate state, and never invoke embedded scripts — installing a skill is a
separate APPROVE-tier flow handled elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Cap body size returned to the LLM. Skills longer than this are excerpted
# so an oversized SKILL.md cannot blow the context budget unintentionally.
MAX_SKILL_BODY_CHARS = 20_000


@dataclass(frozen=True)
class SkillIndexEntry:
    """One row of the cheap skill index — what the planner sees by default."""

    name: str
    summary: str
    permissions: list[str]
    sha256: str


@dataclass(frozen=True)
class SkillBody:
    """The result of loading one skill on demand."""

    name: str
    summary: str
    body: str
    bytes_total: int
    truncated: bool


def skill_index(registry: Any) -> list[SkillIndexEntry]:
    """Return the cheap index — what the planner can scan without bodies."""
    if registry is None or not hasattr(registry, "list"):
        return []
    out: list[SkillIndexEntry] = []
    for manifest in registry.list():
        out.append(
            SkillIndexEntry(
                name=str(getattr(manifest, "name", "")),
                summary=str(getattr(manifest, "summary", "")),
                permissions=list(getattr(manifest, "permissions", []) or []),
                sha256=str(getattr(manifest, "sha256", "")),
            )
        )
    out.sort(key=lambda e: e.name)
    return out


def skill_load(registry: Any, name: str) -> SkillBody:
    """Load one skill's SKILL.md body. Refuses unknown names.

    The body is truncated to :data:`MAX_SKILL_BODY_CHARS` so a misconfigured
    skill (e.g. an accidental log file) can't quietly inflate the context.
    """
    if not name or not str(name).strip():
        raise ValueError("skill_load needs a non-empty name")
    cleaned = str(name).strip()
    if registry is None or not hasattr(registry, "list"):
        raise ValueError("skill registry is not configured")
    match = None
    for manifest in registry.list():
        if str(getattr(manifest, "name", "")) == cleaned:
            match = manifest
            break
    if match is None:
        raise ValueError(f"unknown skill {cleaned!r}")

    skills_dir = getattr(registry, "skills_dir", None)
    if skills_dir is None:
        raise ValueError("skill registry has no skills_dir")
    skill_md = Path(skills_dir) / cleaned / "SKILL.md"
    if not skill_md.exists() or not skill_md.is_file():
        raise ValueError(f"skill {cleaned!r} has no SKILL.md on disk")
    raw = skill_md.read_text(encoding="utf-8")
    truncated = len(raw) > MAX_SKILL_BODY_CHARS
    body = raw[:MAX_SKILL_BODY_CHARS]
    return SkillBody(
        name=cleaned,
        summary=str(getattr(match, "summary", "")),
        body=body,
        bytes_total=len(raw.encode("utf-8")),
        truncated=truncated,
    )
