"""http.fetch — AUTO read over the web, output tagged UNTRUSTED.

The trifecta guard (untrusted + private + egress in one step) blocks any chain
where this output combines with a private read and an egress action — closes
the indirect prompt-injection exfiltration path.

This tool wraps the existing :class:`HttpxFetcher` so the runtime's cached fetcher
keeps working the same way. Output is text only; binary content is rejected.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from midas.core.web.fetch import Fetcher, HttpxFetcher

DEFAULT_FETCHER: Fetcher = HttpxFetcher()
MAX_TEXT_BYTES = 200_000


@dataclass(frozen=True)
class HttpFetchResult:
    url: str
    status: int
    ok: bool
    sha256: str
    text: str  # truncated to MAX_TEXT_BYTES
    truncated: bool


def http_fetch(url: str, *, fetcher: Fetcher | None = None) -> HttpFetchResult:
    if not isinstance(url, str) or not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("http.fetch requires an absolute http(s) URL")
    page = (fetcher or DEFAULT_FETCHER).fetch(url)
    text = page.text or ""
    raw = text.encode("utf-8", errors="replace")
    truncated = len(raw) > MAX_TEXT_BYTES
    if truncated:
        raw = raw[:MAX_TEXT_BYTES]
        text = raw.decode("utf-8", errors="replace")
    return HttpFetchResult(
        url=page.url,
        status=page.status,
        ok=page.ok,
        sha256=hashlib.sha256(raw).hexdigest(),
        text=text,
        truncated=truncated,
    )


def as_tool_payload(result: HttpFetchResult) -> dict[str, Any]:
    return {
        "url": result.url,
        "status": result.status,
        "ok": result.ok,
        "sha256": result.sha256,
        "text_len": len(result.text),
        "truncated": result.truncated,
    }
