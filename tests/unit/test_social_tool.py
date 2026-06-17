"""Phase 4 — social.publish: approval-gated, intent-hash-verified publication.

Contract:
- ``plan_social_publish`` does NOT egress and does NOT read credentials.
- The platform adapter only runs at execute time.
- An intent-hash drift between approval and execute is refused.
- Unknown platform or empty text is rejected up front.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.social import (
    LinkedInAdapter,
    PublishResult,
    SocialAdapterError,
    StubSocialAdapter,
    XTwitterAdapter,
    _hash_intent,
    execute_social_publish,
    plan_social_publish,
    register_adapter,
)


def _guard(tmp_path: Path) -> FsGuard:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return FsGuard(workspace=workspace.resolve())


def test_plan_normalizes_twitter_to_x(tmp_path: Path) -> None:
    plan = plan_social_publish(
        _guard(tmp_path),
        platform="twitter",
        text="hello world",
        account_handle="@me",
    )
    assert plan.platform == "x"
    assert plan.char_count == len("hello world")
    assert plan.sha256_intent == _hash_intent(
        platform="x", handle="@me", text="hello world", media=[]
    )


def test_plan_rejects_empty_text(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty text"):
        plan_social_publish(
            _guard(tmp_path), platform="x", text="   ", account_handle="@me"
        )


def test_plan_rejects_unknown_platform(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported platform"):
        plan_social_publish(
            _guard(tmp_path), platform="myspace", text="hi", account_handle="@me"
        )


def test_plan_rejects_missing_media(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        plan_social_publish(
            _guard(tmp_path),
            platform="x",
            text="hi",
            account_handle="@me",
            media_paths=["nope.png"],
        )


def test_plan_accepts_existing_media(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    media = (guard.workspace / "hero.png")
    media.write_bytes(b"\x89PNG fake")
    plan = plan_social_publish(
        guard,
        platform="x",
        text="hi",
        account_handle="@me",
        media_paths=["hero.png"],
    )
    assert len(plan.media_paths) == 1
    assert plan.media_paths[0].endswith("hero.png")


def test_execute_uses_registered_adapter() -> None:
    register_adapter(StubSocialAdapter())
    payload = {
        "platform": "stub",
        "text": "hello",
        "account_handle": "@me",
        "media_paths": [],
        "sha256_intent": _hash_intent(
            platform="stub", handle="@me", text="hello", media=[]
        ),
    }
    result = execute_social_publish(payload)
    assert isinstance(result, PublishResult)
    assert result.post_id  # deterministic stub
    assert result.permalink.startswith("stub://@me/")
    assert result.cost_usd == 0.0


def test_execute_refuses_intent_drift() -> None:
    """If the text or media changed between approval and execute, refuse."""
    register_adapter(StubSocialAdapter())
    payload = {
        "platform": "stub",
        "text": "different text now",
        "account_handle": "@me",
        "media_paths": [],
        "sha256_intent": _hash_intent(
            platform="stub", handle="@me", text="original text", media=[]
        ),
    }
    with pytest.raises(SocialAdapterError, match="intent hash drifted"):
        execute_social_publish(payload)


def test_execute_refuses_unknown_platform() -> None:
    payload = {
        "platform": "unknown_xyz",
        "text": "hi",
        "account_handle": "@me",
        "media_paths": [],
    }
    with pytest.raises(SocialAdapterError, match="no adapter registered"):
        execute_social_publish(payload)


def test_execute_enforces_adapter_char_limit() -> None:
    register_adapter(StubSocialAdapter(name="strict", max_chars=10))
    payload = {
        "platform": "strict",
        "text": "this text is much too long",
        "account_handle": "@me",
        "media_paths": [],
        "sha256_intent": _hash_intent(
            platform="strict",
            handle="@me",
            text="this text is much too long",
            media=[],
        ),
    }
    with pytest.raises(SocialAdapterError, match="max is 10"):
        execute_social_publish(payload)


def test_x_adapter_without_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    adapter = XTwitterAdapter()
    with pytest.raises(SocialAdapterError, match="X_BEARER_TOKEN"):
        adapter.publish(text="hi", media_paths=[], account_handle="@me")


def test_x_adapter_refuses_media_in_this_slice() -> None:
    adapter = XTwitterAdapter()
    with pytest.raises(SocialAdapterError, match="does not yet upload media"):
        adapter.publish(text="hi", media_paths=["x.png"], account_handle="@me")


def test_linkedin_adapter_without_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINKEDIN_AUTHOR_URN", raising=False)
    adapter = LinkedInAdapter()
    with pytest.raises(SocialAdapterError, match="LINKEDIN_ACCESS_TOKEN"):
        adapter.publish(text="hi", media_paths=[], account_handle="me")


def test_linkedin_adapter_without_author_urn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "fake")
    monkeypatch.delenv("LINKEDIN_AUTHOR_URN", raising=False)
    adapter = LinkedInAdapter()
    with pytest.raises(SocialAdapterError, match="LINKEDIN_AUTHOR_URN"):
        adapter.publish(text="hi", media_paths=[], account_handle="me")


def test_linkedin_adapter_refuses_media_in_this_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "fake")
    monkeypatch.setenv("LINKEDIN_AUTHOR_URN", "urn:li:person:abc")
    adapter = LinkedInAdapter()
    with pytest.raises(SocialAdapterError, match="does not yet upload media"):
        adapter.publish(text="hi", media_paths=["x.png"], account_handle="me")
