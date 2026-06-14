"""Page fetcher — pluggable + mockable. Treats fetched content as UNTRUSTED data.

A `Fetcher` returns a `FetchedPage`. The real `HttpxFetcher` does a GET with a timeout
and a size cap; tests inject a static fetcher. Robots/rate-limit policy lives in the
calling tool layer (Sentinel) — this is just transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FetchedPage:
    url: str
    status: int
    text: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and bool(self.text.strip())


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


class StaticFetcher:
    """Serves pages from a dict; unknown URLs return 404. For tests/offline."""

    def __init__(self, pages: dict[str, str], *, status: int = 200) -> None:
        self._pages = pages
        self._status = status

    def fetch(self, url: str) -> FetchedPage:
        if url not in self._pages:
            return FetchedPage(url=url, status=404, text="")
        return FetchedPage(url=url, status=self._status, text=self._pages[url])


class HttpxFetcher:
    def __init__(self, *, timeout: float = 10.0, max_bytes: int = 1_000_000) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes

    def fetch(self, url: str) -> FetchedPage:
        import httpx  # lazy: only for real calls

        try:
            resp = httpx.get(url, timeout=self._timeout, follow_redirects=True)
        except httpx.HTTPError:
            return FetchedPage(url=url, status=0, text="")
        return FetchedPage(url=url, status=resp.status_code, text=resp.text[: self._max_bytes])
