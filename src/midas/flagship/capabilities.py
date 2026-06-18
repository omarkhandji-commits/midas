"""Local capability discovery and fallback planning.

This is MIDAS's "debrouillard" layer: detect what is already available on the
operator's machine, then explain the cheapest safe path for a requested job.
It never installs, downloads, or calls the network.
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict, dataclass
from typing import Literal

CapabilityStatus = Literal["available", "setup_required", "approval_required", "forbidden"]


@dataclass(frozen=True)
class CapabilityProbe:
    name: str
    status: CapabilityStatus
    category: str
    command: str | None = None
    python_module: str | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityPlan:
    goal: str
    status: CapabilityStatus
    primary_path: str
    fallback_path: str
    approval_required: bool
    privacy_note: str
    cost_note: str
    missing: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def scan_capabilities() -> list[CapabilityProbe]:
    probes = [
        _command("ffmpeg", "media", "Required for robust audio/video muxing."),
        _command("node", "media", "Required for Remotion projects."),
        _command("npx", "media", "Used to run Remotion without a global install."),
        _command("git", "dev", "Required for repo-aware coding workflows."),
        _command("docker", "sandbox", "Optional stronger sandbox for code.run."),
        _command("podman", "sandbox", "Optional stronger sandbox for code.run."),
        _command("ollama", "llm", "Optional local LLM provider."),
        _command("edge-tts", "voice", "Free cloud TTS, no API key, needs internet."),
        _module("kokoro", "voice", "Local/open-weight TTS candidate."),
        _module("piper", "voice", "Fast local CPU TTS candidate."),
        _module("TTS", "voice", "Coqui XTTS voice cloning candidate."),
        _module("neutts", "voice", "NeuTTS local voice candidate."),
    ]
    return probes


def plan_capability(goal: str) -> CapabilityPlan:
    text = goal.lower()
    probes = {p.name: p for p in scan_capabilities()}

    if any(word in text for word in ("video", "remotion", "mp4", "short", "reel")):
        missing = _missing(probes, ["node", "npx", "ffmpeg"])
        status: CapabilityStatus = "available" if not missing else "setup_required"
        return CapabilityPlan(
            goal=goal,
            status=status,
            primary_path=(
                "Use local Remotion plus ffmpeg: script, storyboard, TTS, "
                "captions, render."
            ),
            fallback_path=(
                "If Remotion is missing, create a storyboard package and setup "
                "checklist."
            ),
            approval_required=True,
            privacy_note="Rendering is local. Stock/media downloads need explicit approval.",
            cost_note="Free locally except any chosen LLM or paid media provider.",
            missing=missing,
        )

    if any(word in text for word in ("voice", "tts", "audio", "parle", "speech")):
        local = [
            name
            for name in ("kokoro", "piper", "TTS", "neutts")
            if probes[name].status == "available"
        ]
        edge = probes["edge-tts"].status == "available"
        status = "available" if local or edge else "setup_required"
        primary = (
            "Use local TTS: Kokoro/Piper first, XTTS/NeuTTS for cloning."
            if local
            else "Use Edge TTS as free cloud fallback."
        )
        return CapabilityPlan(
            goal=goal,
            status=status,
            primary_path=primary,
            fallback_path="If no TTS is installed, generate the voice script and setup steps.",
            approval_required=True,
            privacy_note=(
                "Local TTS keeps text on device. Edge TTS sends text to "
                "Microsoft service."
            ),
            cost_note="Local and Edge are free; premium providers stay opt-in.",
            missing=[] if status == "available" else ["kokoro or piper or edge-tts"],
        )

    if any(word in text for word in ("code", "repo", "edit", "bug", "feature")):
        missing = _missing(probes, ["git"])
        return CapabilityPlan(
            goal=goal,
            status="available" if not missing else "setup_required",
            primary_path="Use repo_map, focused file reads, then approval-gated code.edit_plan.",
            fallback_path=(
                "If git is unavailable, use filesystem reads and draft a "
                "manual patch plan."
            ),
            approval_required=True,
            privacy_note="Repo reads stay local; writes require approval.",
            cost_note="Cheap/local model for mapping, smart model only for risky edits.",
            missing=missing,
        )

    if any(word in text for word in ("stripe", "payment", "price", "subscription")):
        return CapabilityPlan(
            goal=goal,
            status="approval_required",
            primary_path=(
                "Draft Stripe intent locally, then execute only after approval "
                "with operator credentials."
            ),
            fallback_path="Create invoice/proposal artifact if Stripe credentials are absent.",
            approval_required=True,
            privacy_note="Stripe secret key is read only at approved execution time.",
            cost_note="No MIDAS fee; Stripe fees are external.",
            missing=[],
        )

    return CapabilityPlan(
        goal=goal,
        status="available",
        primary_path=(
            "Use the native toolset first, then skill index, then a safe "
            "artifact fallback."
        ),
        fallback_path="Create a Markdown best-effort with exact missing dependency notes.",
        approval_required=False,
        privacy_note="Reads and planning stay local unless a tool explicitly needs egress.",
        cost_note="Cheap/local model first; smart model only for high-stakes review.",
        missing=[],
    )


def _command(name: str, category: str, detail: str) -> CapabilityProbe:
    path = shutil.which(name)
    return CapabilityProbe(
        name=name,
        status="available" if path else "setup_required",
        category=category,
        command=path,
        detail=detail,
    )


def _module(name: str, category: str, detail: str) -> CapabilityProbe:
    found = importlib.util.find_spec(name) is not None
    return CapabilityProbe(
        name=name,
        status="available" if found else "setup_required",
        category=category,
        python_module=name,
        detail=detail,
    )


def _missing(probes: dict[str, CapabilityProbe], names: list[str]) -> list[str]:
    return [name for name in names if probes[name].status != "available"]
