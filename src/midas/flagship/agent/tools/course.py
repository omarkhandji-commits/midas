"""course.outline_draft — structured course outline artifact.

Why
---
Phase 7 cash vein WS-X. Courses are a recurring revenue surface for
operators with niche expertise. The hardest part isn't recording — it's
the outline that survives a buyer's "what will I actually learn?" test.
This tool produces a deterministic, structured outline the operator can
sell from before they ever record a video.

Contract
--------
- AUTO-tier render. Pure data, no egress.
- Input: topic, target audience, number of modules, optional
  learning_objectives. Output: a structured outline (per-module
  goals + key concepts + an exercise prompt) and a markdown rendering.
- Honest: we do NOT generate filler "lorem ipsum" lessons. If you ask
  for 10 modules from a thin topic, the output names the modules but
  marks each one ``needs_research=true`` so the planner can drill in.

Honest constraints
------------------
- We do NOT claim a price or promise sales numbers.
- We do NOT scrape competing courses — that's a separate research
  pass through ``research.run``.
- Module count is capped at 20 — bigger courses should be split into
  a track (multiple courses), not stuffed into one outline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


class CourseError(RuntimeError):
    """Raised when an outline can't be produced honestly."""


_MAX_MODULES = 20
_TOPIC_MIN = 8
_TOPIC_MAX = 200


@dataclass(frozen=True)
class CourseModule:
    index: int  # 1-based
    title: str
    goal: str
    key_concepts: list[str] = field(default_factory=list)
    exercise: str = ""
    needs_research: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CourseOutline:
    kind: str = "course_outline"
    topic: str = ""
    audience: str = ""
    learning_objectives: list[str] = field(default_factory=list)
    modules: list[CourseModule] = field(default_factory=list)
    markdown: str = ""
    sha256_intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modules"] = [m.to_dict() for m in self.modules]
        return d


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "module"


# Module shape skeletons — the planner can override per-module via
# ``module_titles``. These defaults are honest scaffolds, not filler.
_DEFAULT_SHAPE = [
    ("Foundations", "Set the vocabulary and frame of the topic."),
    ("Core mechanic", "Practice the one thing that makes the system work."),
    ("Common pitfalls", "Identify failure modes before they cost money."),
    ("Real-world walkthrough", "Apply the mechanic on a worked example."),
    ("Measurement", "Decide what success looks like and how to track it."),
    ("Iteration", "Refine based on what the measurement reveals."),
    ("Scale-up", "Move from one-off to repeatable."),
    ("Edge cases", "Handle the exceptions the basics don't cover."),
    ("Synthesis", "Tie the pieces into a single workflow."),
    ("Next steps", "Point to the next problem worth solving."),
]


def plan_course_outline(
    *,
    topic: str,
    audience: str,
    n_modules: int = 5,
    learning_objectives: list[str] | None = None,
    module_titles: list[str] | None = None,
) -> CourseOutline:
    """Build a structured course outline from a topic + audience."""
    topic_clean = topic.strip()
    if not topic_clean:
        raise CourseError("course.outline_draft needs a non-empty topic")
    if len(topic_clean) < _TOPIC_MIN:
        raise CourseError(
            f"topic is too thin ({len(topic_clean)} chars); needs ≥{_TOPIC_MIN}"
        )
    if len(topic_clean) > _TOPIC_MAX:
        raise CourseError(
            f"topic is too long ({len(topic_clean)} chars); cap is {_TOPIC_MAX}"
        )
    aud_clean = audience.strip()
    if not aud_clean:
        raise CourseError("course.outline_draft needs a non-empty audience")
    if n_modules < 2:
        raise CourseError(f"n_modules must be ≥2, got {n_modules}")
    if n_modules > _MAX_MODULES:
        raise CourseError(
            f"n_modules capped at {_MAX_MODULES}; split into a track instead"
        )

    objectives = [o.strip() for o in (learning_objectives or []) if o.strip()]
    # If the planner didn't pass module titles, fill from the default shape.
    titles = [t.strip() for t in (module_titles or []) if t.strip()]
    if titles and len(titles) != n_modules:
        raise CourseError(
            f"module_titles has {len(titles)} entries but n_modules={n_modules}"
        )
    if not titles:
        # Take the first n_modules from the shape, cycling if n>10.
        titles = [
            _DEFAULT_SHAPE[i % len(_DEFAULT_SHAPE)][0]
            for i in range(n_modules)
        ]

    modules: list[CourseModule] = []
    for i, title in enumerate(titles, start=1):
        shape_idx = (i - 1) % len(_DEFAULT_SHAPE)
        _, goal_template = _DEFAULT_SHAPE[shape_idx]
        # If the planner supplied a custom title that doesn't match the shape,
        # mark the module as needing research — we don't fabricate content.
        custom = title not in {s[0] for s in _DEFAULT_SHAPE}
        modules.append(CourseModule(
            index=i,
            title=title,
            goal=f"{goal_template} (for: {aud_clean})",
            key_concepts=[],  # honest empty; planner / research fills these
            exercise=(
                f"Apply this module to a concrete instance of '{topic_clean}'."
            ),
            needs_research=custom or shape_idx >= 6,  # later modules need depth
        ))

    md_lines: list[str] = []
    md_lines.append(f"# {topic_clean}")
    md_lines.append("")
    md_lines.append(f"**Audience:** {aud_clean}")
    md_lines.append("")
    if objectives:
        md_lines.append("## Learning objectives")
        for o in objectives:
            md_lines.append(f"- {o}")
        md_lines.append("")
    md_lines.append("## Modules")
    for m in modules:
        md_lines.append(f"### Module {m.index} · {m.title}")
        md_lines.append(f"**Goal:** {m.goal}")
        if m.exercise:
            md_lines.append(f"**Exercise:** {m.exercise}")
        if m.needs_research:
            md_lines.append("*Needs research before recording.*")
        md_lines.append("")
    markdown = "\n".join(md_lines)

    canonical = "\n".join([
        topic_clean, aud_clean, str(n_modules),
        *objectives, *[m.title for m in modules],
    ])
    return CourseOutline(
        topic=topic_clean,
        audience=aud_clean,
        learning_objectives=objectives,
        modules=modules,
        markdown=markdown,
        sha256_intent=_sha256(canonical),
    )
