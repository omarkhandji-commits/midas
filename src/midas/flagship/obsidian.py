"""Obsidian vault adapter — read-only, local-first, FsGuard-respected.

What it does. Scans an Obsidian vault on disk and pulls out the operator's:
- recent notes (newest first by mtime),
- project pages (anything tagged ``#project`` or under a ``projects/`` folder),
- decisions (frontmatter ``status: decided`` or filename starting with ``DECISION``).

It does NOT execute templates, run dataview queries, or follow embeds. Every
read is plain text + Markdown. The path is sandboxed: it accepts any directory
the operator passes, but never crosses out of it.

Why this exists. ``midas advise`` reads the vault to ground its proposals in the
operator's real projects (Kenza's Sweet, the agency, etc.) instead of generic
business advice. The Proof-First trail: each note's path is the source.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

_MD = (".md", ".markdown")


@dataclass(frozen=True)
class ObsidianNote:
    path: Path
    title: str
    excerpt: str
    tags: list[str] = field(default_factory=list)
    is_project: bool = False
    mtime: float = 0.0


def _read_excerpt(p: Path, *, max_chars: int = 1200) -> str:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    # Strip frontmatter so previews show real content, not YAML.
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            text = text[end + 4 :].lstrip()
    return text[:max_chars]


def _extract_frontmatter(p: Path) -> dict[str, str]:
    """Read YAML-ish frontmatter (one-line scalars only — no deps)."""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip().lower()] = value.strip().strip('"').strip("'")
    return fm


def _extract_tags(text: str) -> list[str]:
    tags: set[str] = set()
    for token in text.split():
        if token.startswith("#") and len(token) > 1 and token[1].isalpha():
            tags.add(token.strip("#,.;:").lower())
    return sorted(tags)


def _is_project(path: Path, text: str, tags: list[str]) -> bool:
    if any(part.lower() in {"projects", "projets"} for part in path.parts):
        return True
    if "project" in tags or "projet" in tags:
        return True
    if path.name.lower().startswith(("project-", "projet-")):
        return True
    return False


def scan_vault(vault_path: str | Path, *, limit: int = 50) -> list[ObsidianNote]:
    """Return the ``limit`` most-recently-modified notes (newest first).

    Vault must exist; raises ``FileNotFoundError`` otherwise. Reads ``.md`` /
    ``.markdown`` only; binaries and `.obsidian/` plumbing are skipped. Any file
    whose resolved path escapes the vault (via symlink chasing) is dropped — so
    a malicious vault can't trick MIDAS into reading ``~/.ssh/id_rsa``.
    """
    root = Path(vault_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"vault not found: {vault_path}")

    root_str = str(root)
    candidates: list[Path] = []
    for p in root.rglob("*"):
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        if p.suffix.lower() not in _MD:
            continue
        if ".obsidian" in p.parts:
            continue
        # Refuse symlinks whose real target escapes the vault.
        try:
            resolved = p.resolve(strict=False)
        except OSError:
            continue
        sep = "/" if "/" in root_str else "\\"
        if not (str(resolved) == root_str or str(resolved).startswith(root_str + sep)):
            continue
        candidates.append(p)

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[ObsidianNote] = []
    for p in candidates[:limit]:
        text = _read_excerpt(p, max_chars=400)
        tags = _extract_tags(text)
        title = p.stem
        # First non-empty line that isn't frontmatter is a better title.
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(("---", "#")):
                title = line[:120]
                break
        out.append(
            ObsidianNote(
                path=p,
                title=title,
                excerpt=text,
                tags=tags,
                is_project=_is_project(p, text, tags),
                mtime=p.stat().st_mtime,
            )
        )
    return out


def projects(notes: Iterable[ObsidianNote]) -> list[ObsidianNote]:
    return [n for n in notes if n.is_project]


def summarize_vault(notes: list[ObsidianNote], *, max_projects: int = 5) -> str:
    """Compact summary for prompts. Names projects + recent activity."""
    proj = projects(notes)[:max_projects]
    recent = [n for n in notes if not n.is_project][:5]
    lines: list[str] = ["## Operator projects (from Obsidian vault)"]
    if not proj:
        lines.append(
            "- (no project notes detected — tag a note with #project or "
            "use a projects/ folder)"
        )
    for n in proj:
        lines.append(f"- {n.title}  [src: {n.path.name}]")
    if recent:
        lines.append("")
        lines.append("## Recent activity")
        for n in recent:
            lines.append(f"- {n.title}  [src: {n.path.name}]")
    return "\n".join(lines)


__all__ = ["ObsidianNote", "scan_vault", "projects", "summarize_vault"]
