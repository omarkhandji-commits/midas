"""voice.synthesize — same plan/execute pattern as image.draft."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.voice_synth import (
    VoiceBackendError,
    execute_voice_bytes,
    plan_voice_synth,
)


def _guard(tmp_path: Path) -> FsGuard:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return FsGuard(workspace=workspace.resolve())


def test_plan_offline_returns_real_wav(tmp_path: Path) -> None:
    plan = plan_voice_synth(
        _guard(tmp_path),
        "out.wav",
        text="Hello world, this is a test of the offline TTS backend.",
        provider="offline",
    )
    assert plan.kind == "voice"
    assert plan.bytes_len > 0
    raw = base64.b64decode(plan.bytes_b64)
    # WAV header starts with RIFF...WAVE
    assert raw.startswith(b"RIFF")
    assert raw[8:12] == b"WAVE"
    assert plan.sha256_new == hashlib.sha256(raw).hexdigest()
    assert plan.meta["provider"] == "offline"


def test_plan_rejects_empty_text(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty text"):
        plan_voice_synth(_guard(tmp_path), "out.wav", text="   ")


def test_plan_rejects_oversized_text(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="too long"):
        plan_voice_synth(
            _guard(tmp_path), "out.wav", text="x" * 10_000, provider="offline"
        )


def test_plan_rejects_unknown_format(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=".wav or .mp3"):
        plan_voice_synth(_guard(tmp_path), "out.ogg", text="hi")


def test_plan_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown voice provider"):
        plan_voice_synth(
            _guard(tmp_path), "out.wav", text="hi", provider="elevenlabs"
        )


def test_offline_backend_refuses_mp3(tmp_path: Path) -> None:
    """Offline produces WAV only — refuses to mislabel as MP3."""
    with pytest.raises(VoiceBackendError, match=".wav only"):
        plan_voice_synth(
            _guard(tmp_path), "out.mp3", text="hi", provider="offline"
        )


def test_execute_round_trip(tmp_path: Path) -> None:
    plan = plan_voice_synth(
        _guard(tmp_path), "out.wav", text="hello", provider="offline"
    )
    raw = execute_voice_bytes({"bytes_b64": plan.bytes_b64})
    assert raw.startswith(b"RIFF")
    assert hashlib.sha256(raw).hexdigest() == plan.sha256_new


def test_execute_rejects_missing_payload() -> None:
    with pytest.raises(ValueError, match="missing bytes_b64"):
        execute_voice_bytes({})


def test_openai_backend_without_key_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(VoiceBackendError, match="OPENAI_API_KEY"):
        plan_voice_synth(
            _guard(tmp_path), "out.mp3", text="hi", provider="openai"
        )


def test_openai_backend_validates_voice_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    with pytest.raises(VoiceBackendError, match="voice must be"):
        plan_voice_synth(
            _guard(tmp_path),
            "out.mp3",
            text="hi",
            provider="openai",
            voice="celebrity_impersonation",
        )
