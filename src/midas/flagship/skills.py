"""Security-first MIDAS skill registry.

Skills are local folders with a manifest and a SKILL.md. Remote installs are not
performed automatically: MIDAS queues an approval request so the operator can inspect
the source first.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

DENIED_EXTENSIONS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".scr"}
MAX_SKILL_BYTES = 2_000_000


@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str
    summary: str
    permissions: list[str]
    source: str
    sha256: str


class SkillRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.index_path = self.root / "skills.json"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        name: str,
        summary: str,
        permissions: list[str] | None = None,
    ) -> SkillManifest:
        slug = _slug(name)
        target = self.skills_dir / slug
        target.mkdir(parents=True, exist_ok=True)
        skill_md = target / "SKILL.md"
        if not skill_md.exists():
            skill_md.write_text(_skill_template(name, summary), encoding="utf-8")
        manifest = SkillManifest(
            name=slug,
            version="0.1.0",
            summary=summary,
            permissions=permissions or ["read"],
            source="local-created",
            sha256=_tree_hash(target),
        )
        (target / "skill.json").write_text(
            json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._upsert(manifest)
        return manifest

    def install_local(self, source: str | Path) -> SkillManifest:
        src = Path(source)
        _validate_source_tree(src)
        manifest = _read_or_build_manifest(src)
        target = self.skills_dir / _slug(manifest.name)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
        installed = SkillManifest(
            name=_slug(manifest.name),
            version=manifest.version,
            summary=manifest.summary,
            permissions=manifest.permissions,
            source=str(src),
            sha256=_tree_hash(target),
        )
        (target / "skill.json").write_text(
            json.dumps(asdict(installed), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._upsert(installed)
        return installed

    def list(self) -> list[SkillManifest]:
        if not self.index_path.exists():
            return []
        data = json.loads(self.index_path.read_text(encoding="utf-8") or "[]")
        return [SkillManifest(**row) for row in data]

    def _upsert(self, manifest: SkillManifest) -> None:
        rows = [m for m in self.list() if m.name != manifest.name]
        rows.append(manifest)
        self.index_path.write_text(
            json.dumps([asdict(m) for m in rows], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def is_remote_skill_source(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "git", "ssh"}


def _read_or_build_manifest(path: Path) -> SkillManifest:
    manifest_path = path / "skill.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return SkillManifest(
            name=str(data["name"]),
            version=str(data.get("version") or "0.1.0"),
            summary=str(data.get("summary") or ""),
            permissions=[str(p) for p in data.get("permissions", ["read"])],
            source=str(data.get("source") or path),
            sha256=str(data.get("sha256") or _tree_hash(path)),
        )
    skill_md = path / "SKILL.md"
    return SkillManifest(
        name=_slug(path.name),
        version="0.1.0",
        summary=_first_heading(skill_md.read_text(encoding="utf-8")),
        permissions=["read"],
        source=str(path),
        sha256=_tree_hash(path),
    )


def _validate_source_tree(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise ValueError("skill source must be a local directory")
    if not (path / "SKILL.md").exists():
        raise ValueError("skill source must contain SKILL.md")
    total = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        if item.suffix.lower() in DENIED_EXTENSIONS:
            raise ValueError(f"denied executable file in skill: {item.name}")
        total += item.stat().st_size
        if total > MAX_SKILL_BYTES:
            raise ValueError("skill is too large for safe install")


def _tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        if item.name == "skill.json":
            continue
        h.update(str(item.relative_to(path)).replace("\\", "/").encode("utf-8"))
        h.update(item.read_bytes())
    return h.hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("skill name cannot be empty")
    return slug[:64]


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "MIDAS skill"


def _skill_template(name: str, summary: str) -> str:
    return (
        f"---\nname: {_slug(name)}\ndescription: {summary}\n---\n\n"
        f"# {name}\n\n"
        "Use this skill only when the user's request clearly matches its description.\n\n"
        "## Safety\n\n"
        "- Do not send external messages without approval.\n"
        "- Do not access secrets directly.\n"
        "- Keep evidence links and receipts for business decisions.\n"
    )
