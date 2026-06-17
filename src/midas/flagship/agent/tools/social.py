"""Social publish tool — approval-gated post publication.

Contract
--------
- ``plan_social_publish`` validates the post and queues an approval. NO API
  call happens at plan time. The payload carries the normalized text + media
  refs + target platform + sha256 of the canonical post (text+media list).
- ``execute_social_publish`` runs the registered :class:`SocialAdapter` for
  the platform, returns ``PublishResult(post_id, permalink, cost_usd)``. The
  receipt written by the executor tags ``platform`` + ``post_id`` so the
  per-post ROI ledger (``compute_post_roi``) can join cost to revenue.

Adapter protocol
----------------
- ``SocialAdapter.publish(text, media_paths, **kwargs) -> PublishResult``
- Each adapter is responsible for: reading its credentials from the OS
  keychain or env, enforcing the platform's character limit, raising
  :class:`SocialAdapterError` on any failure (the executor records the
  failure as a DENY receipt — bytes are *never* silently lost).

Security envelope
-----------------
- Action: ``publish_public`` (already in default policy's ``requires_approval``).
- Egress: yes (third-party API). Output taint: ``UNTRUSTED`` — the API response
  is data, never instructions for the agent.
- The plan tool refuses empty text and dangling media references. The executor
  refuses if no adapter is registered for the platform — fails loudly, never
  silently no-ops.
- Credentials are only read at *execute* time, never at plan time, so an
  unapproved plan can never trigger egress.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .fsguard import FsGuard


class SocialAdapterError(RuntimeError):
    """Raised when a platform adapter cannot satisfy the publish."""


@dataclass(frozen=True)
class PublishResult:
    """Returned by every adapter — flat, JSON-safe shape for the receipt."""

    post_id: str
    permalink: str
    cost_usd: float = 0.0
    raw_status: str = ""


class SocialAdapter(Protocol):
    """One per platform. Pure function of text + media paths + credentials."""

    name: str
    max_chars: int

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult: ...


@dataclass
class SocialPublishPlan:
    """Approval payload. Bytes are NOT in here — only intent + sha256."""

    kind: str  # always "social_publish"
    platform: str
    account_handle: str
    text: str
    media_paths: list[str]
    char_count: int
    sha256_intent: str  # sha256 of "platform|handle|text|media1\nmedia2..."
    preview: str  # first ~200 chars of text for the approval card
    meta: dict[str, Any] = field(default_factory=dict)


_SUPPORTED_PLATFORMS = {"x", "twitter", "linkedin", "instagram", "facebook", "threads", "youtube"}


def _normalize_platform(platform: str) -> str:
    p = platform.strip().lower()
    if p == "twitter":
        return "x"
    return p


def _hash_intent(*, platform: str, handle: str, text: str, media: list[str]) -> str:
    canonical = "|".join([platform, handle, text, *media])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def plan_social_publish(
    guard: FsGuard,
    *,
    platform: str,
    text: str,
    account_handle: str,
    media_paths: list[str] | None = None,
) -> SocialPublishPlan:
    """Build the approval payload. No egress, no credential read.

    Validates: non-empty text, known platform, every media path resolves inside
    the workspace (FsGuard) and exists. The reviewer sees the exact text and
    sha256 — anything different at execute time would change the hash and the
    receipt would not match the approval.
    """
    if not text.strip():
        raise ValueError("social.publish needs non-empty text")
    if not account_handle.strip():
        raise ValueError("social.publish needs an account_handle")
    norm = _normalize_platform(platform)
    if norm not in _SUPPORTED_PLATFORMS:
        raise ValueError(
            f"unsupported platform {platform!r}; "
            f"supported: {sorted(_SUPPORTED_PLATFORMS)}"
        )

    paths = list(media_paths or [])
    resolved_media: list[str] = []
    for p in paths:
        target = guard.resolve(p)
        if not target.exists() or not target.is_file():
            raise ValueError(f"media path does not exist or is not a file: {p}")
        resolved_media.append(str(target))

    text_clean = text.strip()
    intent_hash = _hash_intent(
        platform=norm, handle=account_handle, text=text_clean, media=resolved_media
    )
    return SocialPublishPlan(
        kind="social_publish",
        platform=norm,
        account_handle=account_handle,
        text=text_clean,
        media_paths=resolved_media,
        char_count=len(text_clean),
        sha256_intent=intent_hash,
        preview=text_clean[:200],
        meta={"n_media": len(resolved_media)},
    )


# ── adapters ─────────────────────────────────────────────────────────────────


_ADAPTERS: dict[str, SocialAdapter] = {}


def register_adapter(adapter: SocialAdapter) -> None:
    """Idempotent registration. Last-write-wins keeps tests simple."""
    _ADAPTERS[adapter.name] = adapter


def get_adapter(platform: str) -> SocialAdapter | None:
    return _ADAPTERS.get(_normalize_platform(platform))


def execute_social_publish(payload: dict[str, Any]) -> PublishResult:
    """Post-approval executor. Reads creds, calls the platform adapter."""
    platform = _normalize_platform(str(payload.get("platform") or ""))
    text = str(payload.get("text") or "")
    handle = str(payload.get("account_handle") or "")
    media = list(payload.get("media_paths") or [])
    if not platform or not text or not handle:
        raise ValueError("social.publish payload is missing required fields")
    # Re-derive the intent hash and refuse to publish if it has drifted from
    # what the operator approved. This is the equivalent of sha256_new on
    # artifacts — a defense against payload tampering between queue and exec.
    expected = str(payload.get("sha256_intent") or "")
    if expected:
        got = _hash_intent(platform=platform, handle=handle, text=text, media=media)
        if got != expected:
            raise SocialAdapterError(
                "publish refused: payload intent hash drifted from approval"
            )

    adapter = _ADAPTERS.get(platform)
    if adapter is None:
        raise SocialAdapterError(
            f"no adapter registered for platform {platform!r}; "
            f"available: {sorted(_ADAPTERS)}"
        )
    if len(text) > adapter.max_chars:
        raise SocialAdapterError(
            f"{platform} max is {adapter.max_chars} chars, got {len(text)}"
        )
    return adapter.publish(text=text, media_paths=media, account_handle=handle)


# ── stub adapter (always available, for tests + dry-run) ─────────────────────


@dataclass
class StubSocialAdapter:
    """Deterministic adapter that records the call without egress.

    Returned ``post_id`` is the first 12 hex chars of sha256(platform+text+handle)
    so tests can assert exact values. Useful for end-to-end approval flow tests
    without configuring real credentials.
    """

    name: str = "stub"
    max_chars: int = 10_000

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        digest = hashlib.sha256(
            f"{self.name}|{account_handle}|{text}".encode()
        ).hexdigest()[:12]
        return PublishResult(
            post_id=digest,
            permalink=f"stub://{account_handle}/{digest}",
            cost_usd=0.0,
            raw_status="stub_ok",
        )


# ── X/Twitter adapter (opt-in, requires TWITTER_BEARER_TOKEN) ────────────────


@dataclass
class XTwitterAdapter:
    """Posts a tweet via the X API v2.

    Requires ``X_BEARER_TOKEN`` (or legacy ``TWITTER_BEARER_TOKEN``) in the
    environment. Media upload is not implemented in this slice — passing media
    raises ``SocialAdapterError`` rather than silently dropping it.
    """

    name: str = "x"
    max_chars: int = 280

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            raise SocialAdapterError(
                "x adapter does not yet upload media — split into a media tool"
            )
        token = os.environ.get("X_BEARER_TOKEN") or os.environ.get(
            "TWITTER_BEARER_TOKEN"
        )
        if not token:
            raise SocialAdapterError(
                "x adapter needs X_BEARER_TOKEN in the environment"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "x adapter needs httpx; install with `pip install httpx`"
            ) from e

        try:
            resp = httpx.post(
                "https://api.twitter.com/2/tweets",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"x publish request failed: {e}") from e
        if resp.status_code not in (200, 201):
            raise SocialAdapterError(
                f"x publish returned {resp.status_code}: {resp.text[:200]}"
            )
        data = (resp.json() or {}).get("data") or {}
        post_id = str(data.get("id") or "")
        if not post_id:
            raise SocialAdapterError("x publish response is missing tweet id")
        return PublishResult(
            post_id=post_id,
            permalink=f"https://twitter.com/{account_handle.lstrip('@')}/status/{post_id}",
            cost_usd=0.0,  # X API pricing varies; the operator records true cost in outcomes
            raw_status="x_ok",
        )


# ── LinkedIn adapter (opt-in, requires LINKEDIN_ACCESS_TOKEN + author URN) ───


@dataclass
class LinkedInAdapter:
    """Posts a text UGC update via the LinkedIn REST API.

    Requires ``LINKEDIN_ACCESS_TOKEN`` (OAuth 2.0 with ``w_member_social`` scope)
    and a ``LINKEDIN_AUTHOR_URN`` (e.g. ``urn:li:person:xxxxxxxx``). LinkedIn
    refuses posts without the author URN — we surface a clear error rather than
    silently picking a default.
    """

    name: str = "linkedin"
    max_chars: int = 3_000

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            raise SocialAdapterError(
                "linkedin adapter does not yet upload media in this slice"
            )
        token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        author = os.environ.get("LINKEDIN_AUTHOR_URN")
        if not token:
            raise SocialAdapterError(
                "linkedin adapter needs LINKEDIN_ACCESS_TOKEN in the environment"
            )
        if not author:
            raise SocialAdapterError(
                "linkedin adapter needs LINKEDIN_AUTHOR_URN (e.g. urn:li:person:xxx)"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "linkedin adapter needs httpx; install with `pip install httpx`"
            ) from e

        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        try:
            resp = httpx.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=body,
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"linkedin publish request failed: {e}") from e
        if resp.status_code not in (200, 201):
            raise SocialAdapterError(
                f"linkedin publish returned {resp.status_code}: {resp.text[:200]}"
            )
        # LinkedIn returns the URN in the `x-restli-id` header or body `id`.
        post_id = resp.headers.get("x-restli-id") or str((resp.json() or {}).get("id") or "")
        if not post_id:
            raise SocialAdapterError("linkedin publish response is missing post id")
        return PublishResult(
            post_id=post_id,
            permalink=f"https://www.linkedin.com/feed/update/{post_id}/",
            cost_usd=0.0,
            raw_status="linkedin_ok",
        )


# Register the stub adapter unconditionally so tests can exercise the full
# plan→approval→execute flow without external credentials. The real adapters
# are registered separately by the runtime when it boots — see runtime.py.
register_adapter(StubSocialAdapter())


def register_default_adapters() -> None:
    """Called by the runtime to wire real platform adapters into the registry.

    Kept as a function (rather than auto-registering) so tests can choose
    whether to swap in stubs. Each adapter only egresses when its ``publish``
    is called — registering it does not trigger any network I/O.
    """
    register_adapter(XTwitterAdapter())
    register_adapter(LinkedInAdapter())


