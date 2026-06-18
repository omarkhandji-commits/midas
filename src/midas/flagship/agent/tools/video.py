"""Video factory primitives: script, storyboard, and Remotion project draft.

The first two tools are pure planning. ``remotion.project.draft`` creates a
real ZIP payload containing a minimal Remotion project. The ZIP is stored in the
approval payload, then written only after approval through the normal FsGuard
write path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import shutil
import subprocess  # nosec B404
import zipfile
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from .fsguard import FsGuard


@dataclass(frozen=True)
class VideoScene:
    index: int
    seconds: float
    narration: str
    visual: str
    caption: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoScript:
    kind: str = "video_script"
    title: str = ""
    audience: str = ""
    goal: str = ""
    duration_seconds: int = 30
    scenes: list[VideoScene] = field(default_factory=list)
    markdown: str = ""
    sha256_intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scenes"] = [scene.to_dict() for scene in self.scenes]
        return data


@dataclass
class RemotionProjectPlan:
    kind: str
    path: str
    bytes_len: int
    sha256_new: str
    sha256_prev: str | None
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)
    bytes_b64: str = ""


@dataclass
class RemotionRenderPlan:
    kind: str
    project_zip: str
    output_path: str
    composition_id: str
    sha256_project: str
    sha256_intent: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemotionRenderResult:
    output_path: str
    sha256_new: str
    bytes_len: int
    exit_code: int


def plan_video_script(
    *,
    title: str,
    audience: str = "operators",
    goal: str = "explain the offer clearly",
    duration_seconds: int = 30,
) -> VideoScript:
    if not title.strip():
        raise ValueError("video.script needs a non-empty title")
    if duration_seconds < 10 or duration_seconds > 180:
        raise ValueError("duration_seconds must be between 10 and 180")
    title_clean = title.strip()
    audience_clean = audience.strip() or "operators"
    goal_clean = goal.strip() or "explain the offer clearly"
    scene_count = max(3, min(6, round(duration_seconds / 10)))
    per_scene = round(duration_seconds / scene_count, 2)
    beats = [
        ("Hook", f"{title_clean}: the problem in one sentence."),
        ("Proof", "Show the current pain, cost, or wasted time."),
        ("Move", "Show the concrete workflow or asset being created."),
        ("Guardrail", "Show approval, receipts, and local-first controls."),
        ("Outcome", "Show what the operator can measure next."),
        ("Close", "Ask for the smallest useful next action."),
    ]
    scenes = [
        VideoScene(
            index=i,
            seconds=per_scene,
            narration=f"{beat}: {line}",
            visual=f"Clean dashboard shot: {beat.lower()} state.",
            caption=line,
        )
        for i, (beat, line) in enumerate(beats[:scene_count], start=1)
    ]
    markdown = _script_markdown(title_clean, audience_clean, goal_clean, scenes)
    return VideoScript(
        title=title_clean,
        audience=audience_clean,
        goal=goal_clean,
        duration_seconds=duration_seconds,
        scenes=scenes,
        markdown=markdown,
        sha256_intent=_sha256(markdown.encode("utf-8")),
    )


def plan_video_storyboard(
    script: dict[str, Any] | VideoScript,
    *,
    aspect: str = "9:16",
) -> dict[str, Any]:
    if aspect not in {"9:16", "16:9", "1:1"}:
        raise ValueError("aspect must be one of 9:16, 16:9, 1:1")
    data = script.to_dict() if isinstance(script, VideoScript) else dict(script)
    scenes = data.get("scenes") or []
    cards = [
        {
            "index": scene.get("index", i),
            "frame": f"{aspect} frame {i}",
            "visual": scene.get("visual", "Dashboard state"),
            "caption": scene.get("caption", ""),
            "motion": "fast cut, readable text, no tiny UI",
        }
        for i, scene in enumerate(scenes, start=1)
        if isinstance(scene, dict)
    ]
    canonical = json.dumps(cards, sort_keys=True, ensure_ascii=False)
    return {
        "kind": "video_storyboard",
        "aspect": aspect,
        "cards": cards,
        "sha256_intent": _sha256(canonical.encode("utf-8")),
    }


def plan_remotion_project(
    guard: FsGuard,
    path: str,
    *,
    title: str,
    script_markdown: str,
    aspect: str = "9:16",
    logo_path: str = "web/public/midas-agent.png",
) -> RemotionProjectPlan:
    target = guard.resolve(path)
    if target.suffix.lower() != ".zip":
        raise ValueError("remotion.project.draft path must end in .zip")
    if aspect not in {"9:16", "16:9", "1:1"}:
        raise ValueError("aspect must be one of 9:16, 16:9, 1:1")
    if not title.strip() or not script_markdown.strip():
        raise ValueError("remotion.project.draft needs title and script_markdown")
    logo = guard.resolve(logo_path) if logo_path else None
    if logo is not None and not logo.exists():
        raise ValueError(f"logo_path does not exist: {logo_path}")

    data = _remotion_zip(
        title=title.strip(),
        script_markdown=script_markdown.strip(),
        aspect=aspect,
        logo_name=logo.name if logo else "",
        logo_bytes=logo.read_bytes() if logo else b"",
    )
    return RemotionProjectPlan(
        kind="remotion_project",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=f"Remotion project ZIP {aspect}: {title[:120]}",
        meta={"title": title.strip(), "aspect": aspect, "logo_path": logo_path},
        bytes_b64=base64.b64encode(data).decode("ascii"),
    )


def execute_remotion_project_bytes(payload: dict[str, Any]) -> bytes:
    b64 = str(payload.get("bytes_b64") or "")
    if not b64:
        raise ValueError("remotion.project.draft payload missing bytes_b64")
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("remotion.project.draft bytes_b64 is not valid base64") from exc
    if not data.startswith(b"PK"):
        raise ValueError("remotion.project.draft payload is not a ZIP")
    return data


def plan_remotion_render(
    guard: FsGuard,
    *,
    project_zip: str,
    output_path: str,
    composition_id: str = "Main",
) -> RemotionRenderPlan:
    """Plan a post-approval Remotion render from a project ZIP."""
    project = guard.resolve(project_zip)
    output = guard.resolve(output_path)
    if not project.exists() or not project.is_file():
        raise ValueError("remotion.render project_zip must exist in the workspace")
    if project.suffix.lower() != ".zip":
        raise ValueError("remotion.render project_zip must be a .zip file")
    if not zipfile.is_zipfile(project):
        raise ValueError("remotion.render project_zip must be a valid ZIP archive")
    if output.suffix.lower() != ".mp4":
        raise ValueError("remotion.render output_path must end in .mp4")
    project_hash = _sha256(project.read_bytes())
    payload = {
        "project_zip": str(project),
        "output_path": str(output),
        "composition_id": composition_id.strip() or "Main",
        "sha256_project": project_hash,
    }
    return RemotionRenderPlan(
        kind="remotion_render",
        project_zip=str(project),
        output_path=str(output),
        composition_id=payload["composition_id"],
        sha256_project=project_hash,
        sha256_intent=_sha256(json.dumps(payload, sort_keys=True).encode("utf-8")),
        preview=f"Render {project.name} -> {output.name}",
        meta={"requires": ["node", "npm", "npx remotion", "ffmpeg"]},
    )


def execute_remotion_render(payload: dict[str, Any]) -> RemotionRenderResult:
    """Run Remotion after approval. Requires local Node/npm/npx."""
    project = Path(str(payload.get("project_zip") or ""))
    output = Path(str(payload.get("output_path") or ""))
    composition_id = str(payload.get("composition_id") or "Main")
    approved_hash = str(payload.get("sha256_project") or "")
    if not project.exists() or not project.is_file():
        raise ValueError("remotion.render project_zip missing")
    current_hash = _sha256(project.read_bytes())
    if approved_hash and current_hash != approved_hash:
        raise ValueError("remotion.render refused: project ZIP drifted since approval")
    intent = {
        "project_zip": str(project),
        "output_path": str(output),
        "composition_id": composition_id,
        "sha256_project": current_hash,
    }
    expected = str(payload.get("sha256_intent") or "")
    if expected and _sha256(json.dumps(intent, sort_keys=True).encode("utf-8")) != expected:
        raise ValueError("remotion.render refused: intent hash drifted")
    npm_bin = shutil.which("npm")
    npx_bin = shutil.which("npx")
    if npm_bin is None or npx_bin is None:
        raise ValueError("remotion.render needs local npm and npx")
    workdir = output.parent / f".midas-remotion-{current_hash[:12]}"
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(project, "r") as zf:
        _safe_extract_zip(zf, workdir)
    install = subprocess.run(  # nosec B603
        [npm_bin, "install", "--silent"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if install.returncode != 0:
        raise ValueError(f"npm install failed: {(install.stderr or install.stdout)[:400]}")
    render = subprocess.run(  # nosec B603
        [
            npx_bin,
            "remotion",
            "render",
            "src/Root.tsx",
            composition_id,
            str(output),
        ],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if render.returncode != 0:
        raise ValueError(f"remotion render failed: {(render.stderr or render.stdout)[:400]}")
    if not output.exists() or output.stat().st_size <= 0:
        raise ValueError("remotion.render produced no MP4")
    data = output.read_bytes()
    return RemotionRenderResult(
        output_path=str(output),
        sha256_new=_sha256(data),
        bytes_len=len(data),
        exit_code=render.returncode,
    )


def _script_markdown(title: str, audience: str, goal: str, scenes: list[VideoScene]) -> str:
    lines = [f"# {title}", "", f"Audience: {audience}", f"Goal: {goal}", "", "## Scenes"]
    for scene in scenes:
        lines.extend(
            [
                "",
                f"### Scene {scene.index} ({scene.seconds}s)",
                f"Narration: {scene.narration}",
                f"Visual: {scene.visual}",
                f"Caption: {scene.caption}",
            ]
        )
    return "\n".join(lines)


def _remotion_zip(
    *,
    title: str,
    script_markdown: str,
    aspect: str,
    logo_name: str,
    logo_bytes: bytes,
) -> bytes:
    width, height = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}[aspect]
    package = {
        "scripts": {
            "start": "remotion studio src/Root.tsx",
            "render": "remotion render src/Root.tsx Main out/video.mp4",
        },
        "dependencies": {
            "@remotion/cli": "latest",
            "remotion": "latest",
            "react": "latest",
            "react-dom": "latest",
        },
        "devDependencies": {"typescript": "latest"},
    }
    root_tsx = f"""import React from 'react';
import {{Composition}} from 'remotion';
import {{Main}} from './Main';

export const RemotionRoot = () => (
  <Composition
    id="Main"
    component={{Main}}
    durationInFrames={{900}}
    fps={{30}}
    width={width}
    height={height}
    defaultProps={{{{ title: {json.dumps(title)}, script: {json.dumps(script_markdown)} }}}}
  />
);
"""
    main_tsx = """import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';

export const Main = ({title, script}: {title: string; script: string}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 24], [0, 1], {extrapolateRight: 'clamp'});
  const lines = script.split('\\n').filter((line) => line.startsWith('Caption:')).slice(0, 5);
  return (
    <AbsoluteFill
      style={{{{background: '#050505', color: '#f4c95d', padding: 72, fontFamily: 'Arial'}}}}
    >
      <div style={{opacity, fontSize: 64, fontWeight: 700, lineHeight: 1.05}}>{title}</div>
      <div style={{marginTop: 72, display: 'grid', gap: 28}}>
        {lines.map((line, index) => (
          <div key={index} style={{{{fontSize: 38, color: '#fff7d6'}}}}>
            {{line.replace('Caption:', '').trim()}}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
"""
    config = "import {Config} from '@remotion/cli/config';\nConfig.setVideoImageFormat('jpeg');\n"
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("package.json", json.dumps(package, indent=2))
        zf.writestr("src/Root.tsx", root_tsx)
        zf.writestr("src/Main.tsx", main_tsx)
        zf.writestr("remotion.config.ts", config)
        zf.writestr("README.md", "# Remotion draft\n\nRun `npm install` then `npm run render`.\n")
        if logo_name and logo_bytes:
            zf.writestr(f"public/{Path(logo_name).name}", logo_bytes)
    return buf.getvalue()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_extract_zip(zf: zipfile.ZipFile, target_dir: Path) -> None:
    base = target_dir.resolve()
    for member in zf.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError("remotion.render refused unsafe ZIP member path")
        destination = (base / member.filename).resolve()
        if not destination.is_relative_to(base):
            raise ValueError("remotion.render refused ZIP path traversal")
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member, "r") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _sha256_prev(target: Path) -> str | None:
    if not target.exists() or not target.is_file():
        return None
    return _sha256(target.read_bytes())
