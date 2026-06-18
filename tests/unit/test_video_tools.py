"""Video factory tools: script, storyboard, and Remotion project draft."""

from __future__ import annotations

import base64
import hashlib
import zipfile
from io import BytesIO
from pathlib import Path

from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.video import (
    execute_remotion_project_bytes,
    plan_remotion_project,
    plan_video_script,
    plan_video_storyboard,
)


def _guard(tmp_path: Path) -> FsGuard:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return FsGuard(workspace=workspace.resolve())


def test_video_script_and_storyboard_are_deterministic() -> None:
    script = plan_video_script(
        title="MIDAS approval center",
        audience="new operators",
        duration_seconds=30,
    )
    storyboard = plan_video_storyboard(script, aspect="9:16")

    assert script.kind == "video_script"
    assert len(script.scenes) >= 3
    assert script.sha256_intent
    assert storyboard["kind"] == "video_storyboard"
    assert storyboard["cards"]
    assert storyboard["sha256_intent"]


def test_remotion_project_draft_returns_real_zip(tmp_path: Path) -> None:
    script = plan_video_script(title="Midas launch short").markdown
    plan = plan_remotion_project(
        _guard(tmp_path),
        "video/midas-remotion.zip",
        title="Midas launch short",
        script_markdown=script,
        logo_path="",
    )
    raw = base64.b64decode(plan.bytes_b64)

    assert raw.startswith(b"PK")
    assert plan.sha256_new == hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(BytesIO(raw)) as zf:
        names = set(zf.namelist())
    assert {"package.json", "src/Root.tsx", "src/Main.tsx", "README.md"} <= names


def test_remotion_project_execute_roundtrip(tmp_path: Path) -> None:
    plan = plan_remotion_project(
        _guard(tmp_path),
        "out.zip",
        title="Roundtrip",
        script_markdown="# Script",
        logo_path="",
    )

    raw = execute_remotion_project_bytes({"bytes_b64": plan.bytes_b64})

    assert hashlib.sha256(raw).hexdigest() == plan.sha256_new
