"""Skill loader on-demand — index returns titles only, body loaded lazily.

The whole point is token economy: a planner can scan the index without
loading bodies, and call ``skill_load`` only for the one it picks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.skill import (
    MAX_SKILL_BODY_CHARS,
    skill_index,
    skill_load,
)
from midas.flagship.skills import SkillRegistry


def _registry_with(tmp_path: Path, *, skills: dict[str, tuple[str, str]]) -> SkillRegistry:
    """skills: {name: (summary, body)} — body becomes SKILL.md contents."""
    reg = SkillRegistry(tmp_path)
    for name, (summary, body) in skills.items():
        reg.create(name=name, summary=summary)
        (reg.skills_dir / name / "SKILL.md").write_text(body, encoding="utf-8")
    return reg


def test_skill_index_returns_sorted_entries(tmp_path: Path) -> None:
    reg = _registry_with(
        tmp_path,
        skills={
            "zebra": ("Last one", "# Zebra"),
            "alpha": ("First one", "# Alpha"),
            "mango": ("Middle one", "# Mango"),
        },
    )
    entries = skill_index(reg)
    assert [e.name for e in entries] == ["alpha", "mango", "zebra"]
    assert entries[0].summary == "First one"


def test_skill_index_handles_no_registry() -> None:
    assert skill_index(None) == []


def test_skill_load_returns_body(tmp_path: Path) -> None:
    body = "# How to draft a Fiverr gig\n\nTalk like a buyer, not a coder."
    reg = _registry_with(tmp_path, skills={"fiverr-gig": ("Fiverr gig draft", body)})
    loaded = skill_load(reg, "fiverr-gig")
    assert loaded.name == "fiverr-gig"
    assert loaded.summary == "Fiverr gig draft"
    assert loaded.body == body
    assert loaded.truncated is False


def test_skill_load_rejects_empty_name(tmp_path: Path) -> None:
    reg = SkillRegistry(tmp_path)
    with pytest.raises(ValueError, match="non-empty"):
        skill_load(reg, "   ")


def test_skill_load_rejects_unknown(tmp_path: Path) -> None:
    reg = _registry_with(tmp_path, skills={"one": ("summary", "body")})
    with pytest.raises(ValueError, match="unknown skill"):
        skill_load(reg, "nope")


def test_skill_load_truncates_oversized_body(tmp_path: Path) -> None:
    huge = "x" * (MAX_SKILL_BODY_CHARS + 5_000)
    reg = _registry_with(tmp_path, skills={"big": ("Big skill", huge)})
    loaded = skill_load(reg, "big")
    assert loaded.truncated is True
    assert len(loaded.body) == MAX_SKILL_BODY_CHARS
    assert loaded.bytes_total > MAX_SKILL_BODY_CHARS


def test_skill_load_refuses_when_no_registry() -> None:
    with pytest.raises(ValueError, match="not configured"):
        skill_load(None, "foo")
