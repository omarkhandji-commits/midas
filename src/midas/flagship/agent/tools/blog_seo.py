"""blog.seo_lint — honest SEO check on a markdown blog post.

Why
---
Phase 7 cash vein WS-V: SEO blog. Before the agent publishes, lint
the markdown for the unglamorous fundamentals — title length, meta
description length, single H1, image alt text, internal links,
heading hierarchy. None of this is magic; it's the checklist every
seasoned content marketer runs through, surfaced as a deterministic
gate so the planner can iterate.

Contract
--------
- AUTO-tier (pure text). No egress, no LLM call, no third-party deps.
- Input: markdown text + optional ``title`` / ``meta_description``
  (front-matter is parsed if present and overrides defaults).
- Output: a structured ``SeoLintResult`` with a 0–100 score and a
  per-issue list with severity. The score is a heuristic, not a
  guarantee of ranking.

Honest constraints
------------------
- We do NOT call a Google API, scrape SERPs, or claim "this will
  rank". SEO scoring without a query + a corpus is fiction; what we
  check are the table-stakes signals well-documented in Google's
  Search Essentials.
- We do NOT auto-fix. Issues land in the result; the planner decides.
- We do NOT pull in markdown-it / mistune. Regex is enough for these
  heuristics and adds zero install footprint.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class SeoIssue:
    code: str  # short stable id, e.g. "title_too_long"
    message: str
    severity: Severity

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeoLintResult:
    score: int = 100  # 0..100, higher is better
    word_count: int = 0
    title: str = ""
    meta_description: str = ""
    h1_count: int = 0
    heading_outline: list[str] = field(default_factory=list)
    image_count: int = 0
    images_missing_alt: int = 0
    internal_links: int = 0
    external_links: int = 0
    issues: list[SeoIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["issues"] = [i.to_dict() for i in self.issues]
        return d


# Tunable thresholds — defaults track Google's documented guidance.
_TITLE_MIN = 30
_TITLE_MAX = 60
_META_MIN = 70
_META_MAX = 160
_WORD_MIN = 300
_PENALTY = {"high": 15, "medium": 8, "low": 3}


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")


def _parse_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Strip a YAML-ish front-matter block and return a flat str→str dict."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, {}
    block = m.group(1)
    rest = text[m.end():]
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return rest, meta


def _word_count(text: str) -> int:
    return len([w for w in re.findall(r"\b\w+\b", text) if w])


def lint_blog(
    *,
    markdown: str,
    title: str = "",
    meta_description: str = "",
    site_domain: str = "",
) -> SeoLintResult:
    """Run the SEO checklist on a markdown post."""
    if not isinstance(markdown, str):
        raise TypeError("blog.seo_lint needs markdown as a string")
    body, frontmatter = _parse_frontmatter(markdown)
    if not title:
        title = frontmatter.get("title", "")
    if not meta_description:
        meta_description = frontmatter.get(
            "description", frontmatter.get("meta_description", "")
        )

    result = SeoLintResult(
        title=title.strip(),
        meta_description=meta_description.strip(),
    )
    result.word_count = _word_count(body)

    # Headings ----------------------------------------------------------------
    headings: list[tuple[int, str]] = []
    for m in _HEADING_RE.finditer(body):
        level = len(m.group(1))
        text = m.group(2).strip()
        headings.append((level, text))
        result.heading_outline.append(f"{'#' * level} {text}")
    result.h1_count = sum(1 for lvl, _ in headings if lvl == 1)

    # Images ------------------------------------------------------------------
    for m in _IMAGE_RE.finditer(body):
        result.image_count += 1
        if not m.group(1).strip():
            result.images_missing_alt += 1

    # Links: internal vs external --------------------------------------------
    site = site_domain.strip().lower()
    for prefix in ("https://", "http://"):
        if site.startswith(prefix):
            site = site[len(prefix):]
            break
    for m in _LINK_RE.finditer(body):
        href = m.group(2).strip().lower()
        if href.startswith(("http://", "https://")):
            if site and site in href:
                result.internal_links += 1
            else:
                result.external_links += 1
        elif href.startswith(("/", "./", "../", "#")):
            result.internal_links += 1
        else:
            result.external_links += 1

    # Issue checks ------------------------------------------------------------
    issues: list[SeoIssue] = []

    if not result.title:
        issues.append(SeoIssue(
            "missing_title",
            "No title provided (front-matter or argument).",
            "high",
        ))
    elif len(result.title) < _TITLE_MIN:
        issues.append(SeoIssue(
            "title_too_short",
            f"Title is {len(result.title)} chars; aim for "
            f"{_TITLE_MIN}–{_TITLE_MAX}.",
            "medium",
        ))
    elif len(result.title) > _TITLE_MAX:
        issues.append(SeoIssue(
            "title_too_long",
            f"Title is {len(result.title)} chars; Google often "
            f"truncates past {_TITLE_MAX}.",
            "medium",
        ))

    if not result.meta_description:
        issues.append(SeoIssue(
            "missing_meta_description",
            "No meta description; the SERP snippet will be auto-generated.",
            "high",
        ))
    elif len(result.meta_description) < _META_MIN:
        issues.append(SeoIssue(
            "meta_too_short",
            f"Meta description is {len(result.meta_description)} chars; "
            f"aim for {_META_MIN}–{_META_MAX}.",
            "low",
        ))
    elif len(result.meta_description) > _META_MAX:
        issues.append(SeoIssue(
            "meta_too_long",
            f"Meta description is {len(result.meta_description)} chars; "
            f"Google truncates past ~{_META_MAX}.",
            "low",
        ))

    if result.h1_count == 0:
        issues.append(SeoIssue(
            "missing_h1",
            "No H1 heading found.",
            "high",
        ))
    elif result.h1_count > 1:
        issues.append(SeoIssue(
            "multiple_h1",
            f"Found {result.h1_count} H1 headings; use exactly one.",
            "medium",
        ))

    # Heading hierarchy: no jumps (h1 → h3 skips h2).
    prev_level = 0
    for level, _ in headings:
        if prev_level and level > prev_level + 1:
            issues.append(SeoIssue(
                "heading_skip",
                f"Heading jumped from H{prev_level} to H{level}; "
                "use one level at a time.",
                "low",
            ))
            break
        prev_level = level

    if result.word_count < _WORD_MIN:
        issues.append(SeoIssue(
            "thin_content",
            f"Body has {result.word_count} words; aim for ≥{_WORD_MIN} "
            "for indexability.",
            "high",
        ))

    if result.images_missing_alt:
        issues.append(SeoIssue(
            "image_missing_alt",
            f"{result.images_missing_alt} image(s) without alt text "
            "(accessibility + SEO).",
            "high",
        ))

    if result.internal_links == 0:
        issues.append(SeoIssue(
            "no_internal_links",
            "No internal links — every post should link to at least one "
            "related page on the same site.",
            "medium",
        ))

    # Compute score -----------------------------------------------------------
    score = 100
    for issue in issues:
        score -= _PENALTY[issue.severity]
    result.score = max(0, score)
    result.issues = issues
    return result
