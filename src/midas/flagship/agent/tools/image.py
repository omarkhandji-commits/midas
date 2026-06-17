"""Image draft tool — provider-agnostic, approval-gated.

Like every other artifact in the cash factory, ``image.draft`` produces bytes at
plan time, stores them in the approval payload (base64), and the post-approval
executor writes them through the existing ``execute_fs_write`` chokepoint. The
reviewer sees the prompt + size + sha256 of the exact bytes before approving —
no surprise content lands on disk.

Backends
--------
- ``offline`` (default): a deterministic Pillow placeholder. Always available
  (Pillow is already a project dep through ``multimodal``). Useful for local
  testing, drafts, and when no provider is configured. The bytes are real PNG
  bytes, not a fake header.
- ``openai``: calls the OpenAI Images API if ``OPENAI_API_KEY`` is configured.
  The image bytes returned by the API land in the approval payload — same
  contract as the offline backend. If the call fails or the key is missing,
  raises ``ImageBackendError`` so the planner can fall back to ``offline``.

Adding a new backend is a one-function change: implement ``generate_bytes`` and
register it in :data:`_BACKENDS`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass, field
from typing import Any

from .fsguard import FsGuard


class ImageBackendError(RuntimeError):
    """Raised when an image backend can't satisfy the request."""


@dataclass
class ImageDraftPlan:
    """Approval payload for an image.draft. ``bytes_b64`` carries the actual PNG."""

    kind: str  # always "image"
    path: str
    bytes_len: int
    sha256_new: str
    sha256_prev: str | None
    preview: str  # human-readable summary, NOT the bytes
    meta: dict[str, Any] = field(default_factory=dict)
    bytes_b64: str = ""  # base64(PNG bytes) — survives JSON serialization


_SUPPORTED_SUFFIXES = {".png"}
_MAX_SIDE = 2048


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_prev(target_path: str) -> str | None:
    from pathlib import Path

    p = Path(target_path)
    if not p.exists() or not p.is_file():
        return None
    return _sha256(p.read_bytes())


def _parse_size(size: str) -> tuple[int, int]:
    if "x" not in size:
        raise ValueError(f"size must be WIDTHxHEIGHT, got {size!r}")
    w_s, h_s = size.split("x", 1)
    try:
        w, h = int(w_s), int(h_s)
    except ValueError as e:
        raise ValueError(f"size must be integers, got {size!r}") from e
    if w <= 0 or h <= 0 or w > _MAX_SIDE or h > _MAX_SIDE:
        raise ValueError(f"size out of bounds (1..{_MAX_SIDE}), got {w}x{h}")
    return w, h


def plan_image(
    guard: FsGuard,
    path: str,
    *,
    prompt: str,
    provider: str = "offline",
    size: str = "512x512",
) -> ImageDraftPlan:
    """Build the approval payload for an image.draft. NO write happens here.

    The PNG bytes are produced by the selected backend and embedded as base64 in
    the payload so the executor can rebuild them byte-for-byte after approval.
    """
    if not prompt.strip():
        raise ValueError("image.draft needs a non-empty prompt")
    target = guard.resolve(path)
    if target.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise ValueError(
            f"image path must end in .png (got {target.suffix!r}); "
            "other formats are not enabled yet"
        )
    width, height = _parse_size(size)

    backend = _BACKENDS.get(provider)
    if backend is None:
        raise ValueError(
            f"unknown image provider {provider!r}; "
            f"available: {sorted(_BACKENDS)}"
        )
    data = backend(prompt=prompt, width=width, height=height)
    if not data.startswith(b"\x89PNG"):
        raise ImageBackendError(
            f"backend {provider!r} did not return a PNG (first bytes look wrong)"
        )

    return ImageDraftPlan(
        kind="image",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(str(target)),
        preview=f"{provider} {width}x{height}: {prompt[:200]}",
        meta={
            "provider": provider,
            "size": f"{width}x{height}",
            "prompt": prompt,
        },
        bytes_b64=base64.b64encode(data).decode("ascii"),
    )


def execute_image_bytes(payload: dict[str, Any]) -> bytes:
    """Decode the approved bytes back from the payload.

    The cash-handler chain in ``execute.py`` calls this builder and pipes the
    bytes through ``execute_fs_write`` (which accepts bytes natively).
    """
    b64 = str(payload.get("bytes_b64") or "")
    if not b64:
        raise ValueError("image.draft payload is missing bytes_b64")
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ValueError("image.draft bytes_b64 is not valid base64") from e
    if not data.startswith(b"\x89PNG"):
        raise ValueError("image.draft payload bytes are not a PNG")
    return data


# ── backends ─────────────────────────────────────────────────────────────────


def _offline_backend(*, prompt: str, width: int, height: int) -> bytes:
    """Deterministic Pillow placeholder.

    Renders the prompt on a neutral canvas. The point is not to be pretty — it's
    to be honest: a real PNG is produced so downstream tools (image inspection,
    file sniffing) work, and the operator sees the prompt rendered so it's
    obvious the image isn't from an AI model.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise ImageBackendError(
            "offline image backend needs Pillow; install with `pip install pillow`"
        ) from e

    from io import BytesIO

    img = Image.new("RGB", (width, height), color=(28, 28, 30))
    draw = ImageDraw.Draw(img)
    # Border for visual signal it's a placeholder, not a real generated image.
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(180, 180, 180), width=2)
    # Word-wrap the prompt to fit the canvas. Pillow default font is bitmap, but
    # it's always available; rendering quality isn't the point.
    margin = 16
    line_height = 14
    max_chars = max(8, (width - 2 * margin) // 7)
    lines = ["[ offline placeholder ]", "", *_wrap(prompt, max_chars)]
    y = margin
    for line in lines:
        if y + line_height > height - margin:
            break
        draw.text((margin, y), line, fill=(230, 230, 230))
        y += line_height

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            out.append("")
            continue
        words = paragraph.split()
        line = ""
        for w in words:
            if not line:
                line = w
            elif len(line) + 1 + len(w) <= width:
                line = f"{line} {w}"
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return out


def _openai_backend(*, prompt: str, width: int, height: int) -> bytes:
    """Call OpenAI Images. Opt-in: requires OPENAI_API_KEY at plan time.

    The bytes are returned to the planner and stored in the approval payload —
    same security envelope as every other artifact. The egress happens with the
    operator's own key and prompt, never with foreign data.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ImageBackendError(
            "openai image backend needs OPENAI_API_KEY in the environment"
        )
    try:
        import httpx
    except ImportError as e:
        raise ImageBackendError(
            "openai backend needs httpx; install with `pip install httpx`"
        ) from e

    # OpenAI Images API only accepts a fixed set of sizes; round to the closest.
    api_size = _nearest_openai_size(width, height)
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-image-1",
                "prompt": prompt,
                "size": api_size,
                "n": 1,
            },
            timeout=60.0,
        )
    except httpx.HTTPError as e:
        raise ImageBackendError(f"openai image request failed: {e}") from e
    if resp.status_code != 200:
        raise ImageBackendError(
            f"openai image returned {resp.status_code}: {resp.text[:200]}"
        )
    payload = resp.json()
    data_list = payload.get("data") or []
    if not data_list:
        raise ImageBackendError("openai image returned an empty data list")
    b64 = data_list[0].get("b64_json")
    if not b64:
        raise ImageBackendError("openai image response missing b64_json")
    try:
        return base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as e:
        raise ImageBackendError("openai image b64_json is not valid base64") from e


def _nearest_openai_size(width: int, height: int) -> str:
    """Map an arbitrary size to the closest OpenAI-supported value."""
    aspect = width / height if height else 1.0
    if aspect < 0.85:
        return "1024x1536"
    if aspect > 1.15:
        return "1536x1024"
    return "1024x1024"


_BACKENDS = {
    "offline": _offline_backend,
    "openai": _openai_backend,
}
