"""voice.synthesize — provider-agnostic TTS, approval-gated.

Sibling of ``image.draft``: planner generates audio bytes at plan time,
stores them base64 in the approval payload, executor writes through
``execute_fs_write``. The reviewer sees the prompt + sha256 + voice +
provider before any file lands on disk.

Backends
--------
- ``offline`` (default, always available): emits a real WAV file using the
  stdlib ``wave`` module — a short tone followed by silence whose duration
  scales with the script length. Honest: this is a placeholder, not TTS.
  The receipt makes that unmistakable.
- ``openai`` (opt-in): calls OpenAI's ``audio/speech`` endpoint when
  ``OPENAI_API_KEY`` is in the environment. Output is real synthesized speech.

Adding ElevenLabs / Azure / a local Piper backend is a single function
plus an entry in ``_BACKENDS``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
import os
import struct
import wave
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from .fsguard import FsGuard


class VoiceBackendError(RuntimeError):
    """Raised when a voice backend can't satisfy the request."""


@dataclass
class VoiceSynthPlan:
    """Approval payload — bytes_b64 carries the actual audio."""

    kind: str  # always "voice"
    path: str
    bytes_len: int
    sha256_new: str
    sha256_prev: str | None
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)
    bytes_b64: str = ""


_SUPPORTED_FORMATS = {".wav", ".mp3"}
_MAX_TEXT_CHARS = 4_000  # OpenAI tts-1 caps at 4096 — we floor below


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_prev(target_path: str) -> str | None:
    from pathlib import Path

    p = Path(target_path)
    if not p.exists() or not p.is_file():
        return None
    return _sha256(p.read_bytes())


def plan_voice_synth(
    guard: FsGuard,
    path: str,
    *,
    text: str,
    provider: str = "offline",
    voice: str = "alloy",
) -> VoiceSynthPlan:
    """Build the approval payload. The audio bytes are produced now and
    embedded so the executor can rebuild them byte-for-byte after approval.
    """
    if not text.strip():
        raise ValueError("voice.synthesize needs non-empty text")
    if len(text) > _MAX_TEXT_CHARS:
        raise ValueError(
            f"voice.synthesize text too long ({len(text)} > {_MAX_TEXT_CHARS})"
        )
    target = guard.resolve(path)
    suffix = target.suffix.lower()
    if suffix not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"voice path must end in .wav or .mp3 (got {suffix!r})"
        )

    backend = _BACKENDS.get(provider)
    if backend is None:
        raise ValueError(
            f"unknown voice provider {provider!r}; "
            f"available: {sorted(_BACKENDS)}"
        )

    data, content_format = backend(text=text, voice=voice, requested_format=suffix)
    # If the backend produced a format the operator didn't ask for, refuse
    # rather than silently rename — the receipt would lie otherwise.
    if content_format != suffix:
        raise VoiceBackendError(
            f"backend {provider!r} returned {content_format} but path requires {suffix}"
        )
    if not data:
        raise VoiceBackendError(f"backend {provider!r} returned empty audio")

    return VoiceSynthPlan(
        kind="voice",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(str(target)),
        preview=f"{provider} ({voice}, {content_format}): {text[:200]}",
        meta={
            "provider": provider,
            "voice": voice,
            "format": content_format,
            "text_chars": len(text),
        },
        bytes_b64=base64.b64encode(data).decode("ascii"),
    )


def execute_voice_bytes(payload: dict[str, Any]) -> bytes:
    """Decode the approved bytes back from the payload (called by execute.py)."""
    b64 = str(payload.get("bytes_b64") or "")
    if not b64:
        raise ValueError("voice.synthesize payload missing bytes_b64")
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError("voice.synthesize bytes_b64 is not valid base64") from e
    if not data:
        raise ValueError("voice.synthesize payload bytes are empty")
    return data


# ── backends ─────────────────────────────────────────────────────────────────


def _offline_backend(
    *, text: str, voice: str, requested_format: str
) -> tuple[bytes, str]:
    """Deterministic stdlib WAV placeholder. Honest about being one.

    Generates a short 440Hz tone for 0.3s + silence for ``len(text)/40`` seconds,
    capped at 30s. The resulting file is a real, playable WAV — downstream
    media-inspection tools work correctly.
    """
    if requested_format != ".wav":
        # The offline backend only knows WAV. Refuse cleanly rather than
        # produce a renamed file.
        raise VoiceBackendError(
            "offline voice backend produces .wav only; "
            f"use provider='openai' for {requested_format}"
        )
    sample_rate = 16_000
    tone_seconds = 0.3
    silence_seconds = min(30.0, max(1.0, len(text) / 40.0))

    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        # Short 440 Hz tone to mark the start (and confirm playability).
        for i in range(int(sample_rate * tone_seconds)):
            sample = int(16_000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            w.writeframes(struct.pack("<h", sample))
        # Silence proportional to script length.
        silent_frames = int(sample_rate * silence_seconds)
        w.writeframes(b"\x00\x00" * silent_frames)
    return buf.getvalue(), ".wav"


def _openai_backend(
    *, text: str, voice: str, requested_format: str
) -> tuple[bytes, str]:
    """Call OpenAI ``audio/speech``. Opt-in: requires OPENAI_API_KEY."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise VoiceBackendError(
            "openai voice backend needs OPENAI_API_KEY in the environment"
        )
    try:
        import httpx
    except ImportError as e:
        raise VoiceBackendError(
            "openai voice backend needs httpx; install with `pip install httpx`"
        ) from e

    # OpenAI accepts a small fixed set of voices and formats. Validate up
    # front rather than passing the call through and getting a 400.
    allowed_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    if voice not in allowed_voices:
        raise VoiceBackendError(
            f"openai voice must be one of {sorted(allowed_voices)}, got {voice!r}"
        )
    response_format = "wav" if requested_format == ".wav" else "mp3"

    try:
        resp = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "voice": voice,
                "input": text,
                "response_format": response_format,
            },
            timeout=60.0,
        )
    except httpx.HTTPError as e:
        raise VoiceBackendError(f"openai voice request failed: {e}") from e
    if resp.status_code != 200:
        raise VoiceBackendError(
            f"openai voice returned {resp.status_code}: {resp.text[:200]}"
        )
    return resp.content, f".{response_format}"


_BACKENDS = {
    "offline": _offline_backend,
    "openai": _openai_backend,
}
