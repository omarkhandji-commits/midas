"""Web search adapters — pluggable, provider-agnostic, mockable.

A `SearchAdapter` returns real `SearchHit`s for a query. Concrete adapters (SearXNG,
Brave) call out over httpx; tests and offline runs use a static adapter. The point is
that Discover can *actually go look* instead of trusting the model to invent URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""


class SearchAdapter(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]: ...


class StaticSearchAdapter:
    """Returns a fixed set of hits — for tests and fully-offline demos."""

    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = hits

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        return self._hits[:limit]


class SearxngSearchAdapter:
    """Query a self-hosted SearXNG instance (privacy-respecting metasearch)."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        import httpx  # lazy: only for real calls

        resp = httpx.get(
            f"{self._base}/search",
            params={"q": query, "format": "json"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])[:limit]
        return [
            SearchHit(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", ""))
            for r in results
            if r.get("url")
        ]
