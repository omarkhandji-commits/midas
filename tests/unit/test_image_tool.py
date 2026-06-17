"""Phase 3 — image.draft: provider-agnostic, approval-gated, bytes-in-payload.

Same contract as cash artifacts: the planner returns the bytes (base64) in the
approval payload, the post-approval executor decodes them and writes through
the existing ``execute_fs_write`` chokepoint.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.image import (
    ImageBackendError,
    execute_image_bytes,
    plan_image,
)

# Pillow is in the ``multimodal`` extra. The offline backend depends on it; the
# error-path tests don't, so we only skip the tests that actually invoke it.
pillow = pytest.importorskip("PIL", reason="image tests need Pillow (multimodal extra)")


def _guard(tmp_path: Path) -> FsGuard:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return FsGuard(workspace=workspace.resolve())


def test_plan_image_offline_returns_real_png(tmp_path: Path) -> None:
    plan = plan_image(
        _guard(tmp_path),
        "out.png",
        prompt="A cozy bakery storefront at sunrise",
        provider="offline",
        size="256x256",
    )
    assert plan.kind == "image"
    assert plan.bytes_len > 0
    assert plan.sha256_new == hashlib.sha256(base64.b64decode(plan.bytes_b64)).hexdigest()
    raw = base64.b64decode(plan.bytes_b64)
    assert raw.startswith(b"\x89PNG"), "offline backend must produce real PNG bytes"
    assert plan.meta["provider"] == "offline"
    assert plan.meta["size"] == "256x256"
    assert "bakery" in plan.meta["prompt"]


def test_plan_image_rejects_empty_prompt(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan_image(
            _guard(tmp_path), "out.png", prompt="   ", provider="offline",
        )


def test_plan_image_rejects_non_png_suffix(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan_image(
            _guard(tmp_path), "out.jpg", prompt="x", provider="offline",
        )


def test_plan_image_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown image provider"):
        plan_image(
            _guard(tmp_path), "out.png", prompt="x", provider="midjourney",
        )


def test_plan_image_rejects_oversized(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        plan_image(
            _guard(tmp_path), "out.png", prompt="x", provider="offline",
            size="9000x9000",
        )


def test_execute_image_bytes_round_trip(tmp_path: Path) -> None:
    plan = plan_image(
        _guard(tmp_path), "out.png", prompt="hello", provider="offline", size="128x128",
    )
    payload = {"bytes_b64": plan.bytes_b64}
    raw = execute_image_bytes(payload)
    assert raw.startswith(b"\x89PNG")
    assert hashlib.sha256(raw).hexdigest() == plan.sha256_new


def test_execute_image_bytes_rejects_non_png() -> None:
    bogus = base64.b64encode(b"not a png").decode("ascii")
    with pytest.raises(ValueError, match="not a PNG"):
        execute_image_bytes({"bytes_b64": bogus})


def test_execute_image_bytes_rejects_missing_payload() -> None:
    with pytest.raises(ValueError, match="missing bytes_b64"):
        execute_image_bytes({})


def test_openai_backend_without_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The openai backend must refuse to run if OPENAI_API_KEY is missing.

    Egress without an explicit operator-configured key would violate the
    'never use someone else's egress to silently call APIs' contract.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageBackendError, match="OPENAI_API_KEY"):
        plan_image(
            _guard(tmp_path), "out.png", prompt="x", provider="openai",
        )
