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


_SUPPORTED_PLATFORMS = {
    "x", "twitter", "linkedin", "instagram", "facebook",
    "threads", "youtube", "reddit", "tiktok",
}


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


# ── Reddit adapter (opt-in, requires Reddit script-type app credentials) ─────


@dataclass
class RedditAdapter:
    """Posts a self (text) submission via the Reddit API.

    Requires a Reddit script-type OAuth app and four env vars:
    ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, ``REDDIT_USERNAME``,
    ``REDDIT_PASSWORD``. We use the password grant because it's the only flow
    Reddit supports for script apps; production apps would use refresh tokens
    instead — wiring that in is a one-line change in ``_oauth_token``.

    Posting needs a target subreddit; we read it from ``account_handle``
    (which carries ``r/<sub>`` for this adapter — same field, different
    semantics per platform). This is honest: Reddit posts are sub-scoped,
    not handle-scoped.
    """

    name: str = "reddit"
    max_chars: int = 40_000

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            raise SocialAdapterError(
                "reddit adapter posts text only in this slice; "
                "image/link posts arrive next"
            )
        sub = account_handle.strip().lstrip("/")
        if sub.lower().startswith("r/"):
            sub = sub[2:]
        if not sub:
            raise SocialAdapterError(
                "reddit needs the subreddit in account_handle (e.g. 'r/Entrepreneur')"
            )
        # First line of text is the title; rest is the body. This matches the
        # newsletter / outreach pattern the cash artifacts already produce.
        lines = text.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if not title:
            raise SocialAdapterError(
                "reddit post needs a title (first line of text)"
            )
        if len(title) > 300:
            raise SocialAdapterError(
                f"reddit title max is 300 chars, got {len(title)}"
            )

        token = _reddit_oauth_token()
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "reddit adapter needs httpx; install with `pip install httpx`"
            ) from e

        try:
            resp = httpx.post(
                "https://oauth.reddit.com/api/submit",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "midas-agent/1.0 (cash operator)",
                },
                data={
                    "sr": sub,
                    "kind": "self",
                    "title": title,
                    "text": body,
                    "api_type": "json",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"reddit submit request failed: {e}") from e
        if resp.status_code != 200:
            raise SocialAdapterError(
                f"reddit /api/submit returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        json_body = (resp.json() or {}).get("json") or {}
        if json_body.get("errors"):
            raise SocialAdapterError(
                f"reddit refused the post: {json_body['errors']}"
            )
        data = json_body.get("data") or {}
        post_url = str(data.get("url") or "")
        post_id = str(data.get("name") or "")  # t3_xxxx
        if not post_id:
            raise SocialAdapterError("reddit response is missing post fullname")
        return PublishResult(
            post_id=post_id,
            permalink=post_url or f"https://reddit.com/r/{sub}/comments/{post_id}",
            cost_usd=0.0,
            raw_status="reddit_ok",
        )


def _reddit_oauth_token() -> str:
    """Exchange Reddit script-app password creds for a short-lived bearer."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")
    missing = [
        n for n, v in (
            ("REDDIT_CLIENT_ID", client_id),
            ("REDDIT_CLIENT_SECRET", client_secret),
            ("REDDIT_USERNAME", username),
            ("REDDIT_PASSWORD", password),
        ) if not v
    ]
    if missing:
        raise SocialAdapterError(
            f"reddit adapter needs env vars: {', '.join(missing)}"
        )
    try:
        import httpx
    except ImportError as e:
        raise SocialAdapterError(
            "reddit adapter needs httpx; install with `pip install httpx`"
        ) from e
    try:
        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id or "", client_secret or ""),
            data={"grant_type": "password", "username": username, "password": password},
            headers={"User-Agent": "midas-agent/1.0 (cash operator)"},
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise SocialAdapterError(f"reddit token request failed: {e}") from e
    if resp.status_code != 200:
        raise SocialAdapterError(
            f"reddit /api/v1/access_token returned {resp.status_code}: "
            f"{resp.text[:200]}"
        )
    token = str((resp.json() or {}).get("access_token") or "")
    if not token:
        raise SocialAdapterError("reddit token response is missing access_token")
    return token


# ── Instagram adapter (opt-in, requires Meta Graph API credentials) ──────────


@dataclass
class InstagramAdapter:
    """Posts an image (with caption) via the Meta Graph API.

    Requires ``INSTAGRAM_ACCESS_TOKEN`` (long-lived) and ``INSTAGRAM_USER_ID``
    (Business or Creator account, NOT a personal account). The flow is
    two-step: create a media container (``/{user_id}/media``), then publish
    it (``/{user_id}/media_publish``).

    Honest constraint: Instagram does **not** support text-only posts via the
    API. Media is required. We refuse the call up front with a clear message
    rather than silently degrade.
    """

    name: str = "instagram"
    max_chars: int = 2_200  # caption limit

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if not media_paths:
            raise SocialAdapterError(
                "instagram requires media (image/video); text-only posts "
                "are not supported by the Instagram Graph API"
            )
        if len(media_paths) > 10:
            raise SocialAdapterError(
                f"instagram carousel cap is 10 images, got {len(media_paths)}"
            )
        for ref in media_paths:
            if not ref.startswith(("http://", "https://")):
                raise SocialAdapterError(
                    "instagram media must be public https URLs the API can fetch; "
                    "upload to S3 / Cloudinary first and pass the URL"
                )
        token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        user_id = os.environ.get("INSTAGRAM_USER_ID")
        if not token:
            raise SocialAdapterError(
                "instagram adapter needs INSTAGRAM_ACCESS_TOKEN in the environment"
            )
        if not user_id:
            raise SocialAdapterError(
                "instagram adapter needs INSTAGRAM_USER_ID "
                "(Business or Creator account id, NOT a personal account)"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "instagram adapter needs httpx; install with `pip install httpx`"
            ) from e

        graph = "https://graph.facebook.com/v19.0"
        if len(media_paths) == 1:
            # Single-image fast path: one container, caption inline.
            try:
                container = httpx.post(
                    f"{graph}/{user_id}/media",
                    data={
                        "image_url": media_paths[0],
                        "caption": text,
                        "access_token": token,
                    },
                    timeout=30.0,
                )
            except httpx.HTTPError as e:
                raise SocialAdapterError(
                    f"instagram container request failed: {e}"
                ) from e
            if container.status_code != 200:
                raise SocialAdapterError(
                    f"instagram /media returned {container.status_code}: "
                    f"{container.text[:200]}"
                )
            container_id = str((container.json() or {}).get("id") or "")
            if not container_id:
                raise SocialAdapterError(
                    "instagram container response is missing id"
                )
        else:
            # Carousel: each child is its own container without caption, then
            # a parent CAROUSEL container that references them by id.
            child_ids: list[str] = []
            for url in media_paths:
                try:
                    child = httpx.post(
                        f"{graph}/{user_id}/media",
                        data={
                            "image_url": url,
                            "is_carousel_item": "true",
                            "access_token": token,
                        },
                        timeout=30.0,
                    )
                except httpx.HTTPError as e:
                    raise SocialAdapterError(
                        f"instagram carousel child request failed: {e}"
                    ) from e
                if child.status_code != 200:
                    raise SocialAdapterError(
                        f"instagram carousel child {len(child_ids)} returned "
                        f"{child.status_code}: {child.text[:200]}"
                    )
                cid = str((child.json() or {}).get("id") or "")
                if not cid:
                    raise SocialAdapterError(
                        "instagram carousel child response is missing id"
                    )
                child_ids.append(cid)
            try:
                parent = httpx.post(
                    f"{graph}/{user_id}/media",
                    data={
                        "media_type": "CAROUSEL",
                        "children": ",".join(child_ids),
                        "caption": text,
                        "access_token": token,
                    },
                    timeout=30.0,
                )
            except httpx.HTTPError as e:
                raise SocialAdapterError(
                    f"instagram carousel parent request failed: {e}"
                ) from e
            if parent.status_code != 200:
                raise SocialAdapterError(
                    f"instagram carousel parent returned {parent.status_code}: "
                    f"{parent.text[:200]}"
                )
            container_id = str((parent.json() or {}).get("id") or "")
            if not container_id:
                raise SocialAdapterError(
                    "instagram carousel parent response is missing id"
                )

        try:
            publish = httpx.post(
                f"{graph}/{user_id}/media_publish",
                data={"creation_id": container_id, "access_token": token},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"instagram publish request failed: {e}") from e
        if publish.status_code != 200:
            raise SocialAdapterError(
                f"instagram /media_publish returned {publish.status_code}: "
                f"{publish.text[:200]}"
            )
        post_id = str((publish.json() or {}).get("id") or "")
        if not post_id:
            raise SocialAdapterError("instagram publish response is missing id")
        return PublishResult(
            post_id=post_id,
            permalink=f"https://www.instagram.com/p/{post_id}/",
            cost_usd=0.0,
            raw_status="instagram_ok",
        )


# ── Facebook adapter (Pages, opt-in) ─────────────────────────────────────────


@dataclass
class FacebookAdapter:
    """Posts a text update to a Facebook Page via the Meta Graph API.

    Requires ``FACEBOOK_PAGE_TOKEN`` (Page access token, not user token) and
    ``FACEBOOK_PAGE_ID``. Posting to a personal profile is no longer supported
    by Meta's API since 2018; this adapter is Pages-only. We refuse early
    rather than letting Meta return a confusing permission error.
    """

    name: str = "facebook"
    max_chars: int = 63_206  # Facebook's stated limit

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            raise SocialAdapterError(
                "facebook adapter posts text only in this slice; "
                "photo + link posts arrive next"
            )
        token = os.environ.get("FACEBOOK_PAGE_TOKEN")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        if not token:
            raise SocialAdapterError(
                "facebook adapter needs FACEBOOK_PAGE_TOKEN "
                "(a Page access token, NOT a user token)"
            )
        if not page_id:
            raise SocialAdapterError(
                "facebook adapter needs FACEBOOK_PAGE_ID"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "facebook adapter needs httpx; install with `pip install httpx`"
            ) from e

        try:
            resp = httpx.post(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                data={"message": text, "access_token": token},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"facebook publish request failed: {e}") from e
        if resp.status_code != 200:
            raise SocialAdapterError(
                f"facebook /feed returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        post_id = str((resp.json() or {}).get("id") or "")
        if not post_id:
            raise SocialAdapterError("facebook publish response is missing id")
        # Page post ids are <page_id>_<post_id>; permalink works either way.
        return PublishResult(
            post_id=post_id,
            permalink=f"https://www.facebook.com/{post_id}",
            cost_usd=0.0,
            raw_status="facebook_ok",
        )


# ── Threads adapter (Meta's text-first network, opt-in) ──────────────────────


@dataclass
class ThreadsAdapter:
    """Posts a text update to Threads via the Meta Threads API.

    Requires ``THREADS_ACCESS_TOKEN`` and ``THREADS_USER_ID``. The flow
    mirrors Instagram's: create a media container, then publish. Threads
    text posts use ``media_type=TEXT`` (no media required, unlike Instagram).
    """

    name: str = "threads"
    max_chars: int = 500  # Threads' character limit

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            raise SocialAdapterError(
                "threads adapter posts text only in this slice; "
                "image attachments arrive next"
            )
        token = os.environ.get("THREADS_ACCESS_TOKEN")
        user_id = os.environ.get("THREADS_USER_ID")
        if not token:
            raise SocialAdapterError(
                "threads adapter needs THREADS_ACCESS_TOKEN in the environment"
            )
        if not user_id:
            raise SocialAdapterError(
                "threads adapter needs THREADS_USER_ID"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "threads adapter needs httpx; install with `pip install httpx`"
            ) from e

        graph = "https://graph.threads.net/v1.0"
        try:
            container = httpx.post(
                f"{graph}/{user_id}/threads",
                data={
                    "media_type": "TEXT",
                    "text": text,
                    "access_token": token,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"threads container request failed: {e}") from e
        if container.status_code != 200:
            raise SocialAdapterError(
                f"threads /threads returned {container.status_code}: "
                f"{container.text[:200]}"
            )
        container_id = str((container.json() or {}).get("id") or "")
        if not container_id:
            raise SocialAdapterError("threads container response is missing id")

        try:
            publish = httpx.post(
                f"{graph}/{user_id}/threads_publish",
                data={"creation_id": container_id, "access_token": token},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"threads publish request failed: {e}") from e
        if publish.status_code != 200:
            raise SocialAdapterError(
                f"threads /threads_publish returned {publish.status_code}: "
                f"{publish.text[:200]}"
            )
        post_id = str((publish.json() or {}).get("id") or "")
        if not post_id:
            raise SocialAdapterError("threads publish response is missing id")
        return PublishResult(
            post_id=post_id,
            permalink=f"https://www.threads.net/@{account_handle.lstrip('@')}/post/{post_id}",
            cost_usd=0.0,
            raw_status="threads_ok",
        )


# ── YouTube adapter (Community posts — opt-in) ───────────────────────────────


@dataclass
class YouTubeAdapter:
    """Posts a Community tab update via the YouTube Data API v3.

    YouTube's video upload flow is resumable + multi-part and depends on an
    actual video file. That ships next. THIS adapter handles the
    text/image-only Community posts (eligible channels: 500+ subscribers as
    of late 2025), which are a real cash-relevant surface: announcements,
    polls, product links.

    Requires ``YOUTUBE_OAUTH_TOKEN`` (OAuth 2.0 with ``youtube`` scope) and
    ``YOUTUBE_CHANNEL_ID``. The token MUST be a user OAuth token, NOT an
    API key — Community posts are a write operation, scoped to the owning
    account.
    """

    name: str = "youtube"
    max_chars: int = 1_000  # YouTube Community post limit

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if media_paths:
            return self._upload_video(text=text, media_paths=media_paths)
        token = os.environ.get("YOUTUBE_OAUTH_TOKEN")
        channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
        if not token:
            raise SocialAdapterError(
                "youtube adapter needs YOUTUBE_OAUTH_TOKEN "
                "(user OAuth token with 'youtube' scope, NOT an API key)"
            )
        if not channel_id:
            raise SocialAdapterError(
                "youtube adapter needs YOUTUBE_CHANNEL_ID"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "youtube adapter needs httpx; install with `pip install httpx`"
            ) from e

        # The Community Posts endpoint is part of the YouTube Data API v3.
        # Note: Google has historically rate-limited this for new channels —
        # the API returns 403 with a clear message we surface as-is.
        try:
            resp = httpx.post(
                "https://www.googleapis.com/youtube/v3/communityPosts",
                params={"part": "snippet"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "snippet": {
                        "channelId": channel_id,
                        "content": {"text": text},
                    },
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"youtube publish request failed: {e}") from e
        if resp.status_code not in (200, 201):
            raise SocialAdapterError(
                f"youtube /communityPosts returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        post_id = str((resp.json() or {}).get("id") or "")
        if not post_id:
            raise SocialAdapterError("youtube response is missing post id")
        return PublishResult(
            post_id=post_id,
            permalink=f"https://www.youtube.com/post/{post_id}",
            cost_usd=0.0,
            raw_status="youtube_ok",
        )

    def _upload_video(
        self, *, text: str, media_paths: list[str]
    ) -> PublishResult:
        """Resumable video upload via /upload/youtube/v3/videos.

        Two steps: (1) start a resumable session with metadata, get the
        upload URL from the Location header; (2) PUT the video bytes.
        Title comes from the first 100 chars of ``text`` (YouTube cap);
        the remainder becomes the description. Privacy defaults to
        ``private`` — the operator flips it to public/unlisted manually
        once they've reviewed the upload in YouTube Studio.
        """
        if len(media_paths) > 1:
            raise SocialAdapterError(
                "youtube video upload takes a single file; got "
                f"{len(media_paths)} paths"
            )
        from pathlib import Path as _Path

        video_path = _Path(media_paths[0])
        if not video_path.is_file():
            raise SocialAdapterError(
                f"youtube video file not found: {video_path}"
            )
        token = os.environ.get("YOUTUBE_OAUTH_TOKEN")
        if not token:
            raise SocialAdapterError(
                "youtube adapter needs YOUTUBE_OAUTH_TOKEN "
                "(user OAuth token with 'youtube.upload' scope)"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "youtube adapter needs httpx; install with `pip install httpx`"
            ) from e

        title = text.strip().split("\n", 1)[0][:100] or "Untitled"
        privacy = os.environ.get("YOUTUBE_PRIVACY", "private").strip().lower()
        if privacy not in ("private", "public", "unlisted"):
            raise SocialAdapterError(
                f"youtube privacy must be private/public/unlisted, got {privacy!r}"
            )
        size = video_path.stat().st_size
        metadata = {
            "snippet": {"title": title, "description": text},
            "status": {"privacyStatus": privacy},
        }
        try:
            start = httpx.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(size),
                    "X-Upload-Content-Type": "video/*",
                },
                json=metadata,
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(
                f"youtube upload session start failed: {e}"
            ) from e
        if start.status_code != 200:
            raise SocialAdapterError(
                f"youtube upload init returned {start.status_code}: "
                f"{start.text[:200]}"
            )
        upload_url = start.headers.get("Location") or start.headers.get("location")
        if not upload_url:
            raise SocialAdapterError(
                "youtube upload init missing Location header"
            )
        try:
            with video_path.open("rb") as fh:
                up = httpx.put(
                    upload_url,
                    content=fh.read(),
                    headers={"Content-Type": "video/*"},
                    timeout=600.0,
                )
        except httpx.HTTPError as e:
            raise SocialAdapterError(
                f"youtube video PUT failed: {e}"
            ) from e
        if up.status_code not in (200, 201):
            raise SocialAdapterError(
                f"youtube video PUT returned {up.status_code}: {up.text[:200]}"
            )
        video_id = str((up.json() or {}).get("id") or "")
        if not video_id:
            raise SocialAdapterError("youtube upload response missing video id")
        return PublishResult(
            post_id=video_id,
            permalink=f"https://www.youtube.com/watch?v={video_id}",
            cost_usd=0.0,
            raw_status=f"youtube_video_{privacy}",
        )


# ── TikTok adapter (Content Posting API — opt-in) ────────────────────────────


@dataclass
class TikTokAdapter:
    """Posts a text-only photo carousel via TikTok's Content Posting API.

    TikTok's API is video-first; text-only posts are not supported. The
    Content Posting API v2 requires a published image or video. For text
    drafts the agent should compose an image via ``image.draft`` first, then
    publish the result here as a photo post.

    Requires ``TIKTOK_ACCESS_TOKEN`` and ``TIKTOK_OPEN_ID``. The first call
    initializes a publish session and uploads the media; the second polls
    for completion. We ship the *initialize* step only in this slice — the
    poll loop is a follow-up — and refuse the call if media isn't a
    publicly-reachable URL the TikTok backend can fetch.
    """

    name: str = "tiktok"
    max_chars: int = 2_200  # TikTok caption limit

    def publish(
        self,
        *,
        text: str,
        media_paths: list[str],
        account_handle: str,
    ) -> PublishResult:
        if not media_paths:
            raise SocialAdapterError(
                "tiktok requires media (image or video); text-only posts "
                "are not supported by the TikTok Content Posting API"
            )
        if len(media_paths) > 1:
            raise SocialAdapterError(
                "tiktok adapter ships single-media posts only in this slice; "
                "multi-photo carousel arrives next"
            )
        media_ref = media_paths[0]
        if not media_ref.startswith(("http://", "https://")):
            raise SocialAdapterError(
                "tiktok media must be a public https URL the API can fetch; "
                "upload to S3 / Cloudinary first and pass the URL"
            )
        token = os.environ.get("TIKTOK_ACCESS_TOKEN")
        open_id = os.environ.get("TIKTOK_OPEN_ID")
        if not token:
            raise SocialAdapterError(
                "tiktok adapter needs TIKTOK_ACCESS_TOKEN in the environment"
            )
        if not open_id:
            raise SocialAdapterError(
                "tiktok adapter needs TIKTOK_OPEN_ID"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "tiktok adapter needs httpx; install with `pip install httpx`"
            ) from e

        # Initialize a photo post session.
        try:
            init = httpx.post(
                "https://open.tiktokapis.com/v2/post/publish/content/init/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "post_info": {
                        "title": text[:90],
                        "description": text,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "photo_cover_index": 0,
                        "photo_images": [media_ref],
                    },
                    "post_mode": "DIRECT_POST",
                    "media_type": "PHOTO",
                },
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SocialAdapterError(f"tiktok init request failed: {e}") from e
        if init.status_code != 200:
            raise SocialAdapterError(
                f"tiktok /publish/content/init returned {init.status_code}: "
                f"{init.text[:200]}"
            )
        data = (init.json() or {}).get("data") or {}
        publish_id = str(data.get("publish_id") or "")
        if not publish_id:
            raise SocialAdapterError("tiktok init response is missing publish_id")
        # If the operator opted in to status polling, block until the post is
        # processed (or fails). Polling defaults OFF — returning pending is
        # honest and lets the agent move on.
        if os.environ.get("TIKTOK_POLL", "").strip() in ("1", "true", "yes"):
            final = self.fetch_status(publish_id=publish_id, token=token)
            return final
        return PublishResult(
            post_id=publish_id,
            permalink=f"https://www.tiktok.com/@{account_handle.lstrip('@')}",
            cost_usd=0.0,
            raw_status="tiktok_pending",
        )

    def fetch_status(
        self,
        *,
        publish_id: str,
        token: str | None = None,
        max_polls: int = 6,
        delay_seconds: float = 5.0,
    ) -> PublishResult:
        """Poll TikTok's /publish/status/fetch/ until terminal or budget runs out.

        Terminal states are ``PUBLISH_COMPLETE`` (success — returns the
        post id) and ``FAILED`` (raises with the surfaced reason). All
        other states (``PROCESSING_DOWNLOAD``, ``PROCESSING_UPLOAD``,
        ``PROCESSING_PUBLISH``) cause another poll up to ``max_polls``.

        Honest: TikTok's terminal post URL only contains the final
        video/photo id, not the publish_id. If we exhaust the budget,
        we return ``tiktok_pending`` so the caller knows status is
        unknown — never invent a permalink we can't verify.
        """
        tok = token or os.environ.get("TIKTOK_ACCESS_TOKEN")
        if not tok:
            raise SocialAdapterError(
                "tiktok status poll needs TIKTOK_ACCESS_TOKEN"
            )
        try:
            import httpx
        except ImportError as e:
            raise SocialAdapterError(
                "tiktok adapter needs httpx; install with `pip install httpx`"
            ) from e
        import time as _time

        for _ in range(max(1, max_polls)):
            try:
                resp = httpx.post(
                    "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                    headers={
                        "Authorization": f"Bearer {tok}",
                        "Content-Type": "application/json",
                    },
                    json={"publish_id": publish_id},
                    timeout=20.0,
                )
            except httpx.HTTPError as e:
                raise SocialAdapterError(
                    f"tiktok status fetch failed: {e}"
                ) from e
            if resp.status_code != 200:
                raise SocialAdapterError(
                    f"tiktok status fetch returned {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
            data = (resp.json() or {}).get("data") or {}
            status = str(data.get("status") or "").upper()
            if status == "PUBLISH_COMPLETE":
                publicaly_available_post_id = str(
                    data.get("publicaly_available_post_id")
                    or data.get("post_id")
                    or publish_id
                )
                return PublishResult(
                    post_id=publicaly_available_post_id,
                    permalink=(
                        f"https://www.tiktok.com/@/video/"
                        f"{publicaly_available_post_id}"
                    ),
                    cost_usd=0.0,
                    raw_status="tiktok_ok",
                )
            if status == "FAILED":
                reason = str(data.get("fail_reason") or "unknown reason")
                raise SocialAdapterError(
                    f"tiktok publish failed: {reason}"
                )
            _time.sleep(delay_seconds)
        # Budget exhausted — honest: we don't know the outcome.
        return PublishResult(
            post_id=publish_id,
            permalink="",
            cost_usd=0.0,
            raw_status="tiktok_pending_timeout",
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
    register_adapter(RedditAdapter())
    register_adapter(InstagramAdapter())
    register_adapter(FacebookAdapter())
    register_adapter(ThreadsAdapter())
    register_adapter(YouTubeAdapter())
    register_adapter(TikTokAdapter())


