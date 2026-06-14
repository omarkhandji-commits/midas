"""Cache-aware decorators around the SearchAdapter and Fetcher protocols.

Keep the originals pure (a single responsibility each) and layer caching on top so
that any adapter — static, SearXNG, Brave, custom — becomes free to reuse across
runs. Misses fall through to the wrapped adapter; hits skip the network.
"""

from __future__ import annotations

import json

from midas.core.cache import ResearchCache, cache_key

from .fetch import FetchedPage, Fetcher
from .search import SearchAdapter, SearchHit


class CachedSearchAdapter:
    def __init__(self, inner: SearchAdapter, cache: ResearchCache) -> None:
        self._inner = inner
        self._cache = cache

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        key = cache_key("search", query, limit)
        hit = self._cache.get(key)
        if hit is not None:
            return [SearchHit(**h) for h in json.loads(hit)]
        results = self._inner.search(query, limit=limit)
        self._cache.put(
            key, json.dumps([h.__dict__ for h in results]), kind="search"
        )
        return results


class CachedFetcher:
    def __init__(self, inner: Fetcher, cache: ResearchCache) -> None:
        self._inner = inner
        self._cache = cache

    def fetch(self, url: str) -> FetchedPage:
        key = cache_key("fetch", url)
        hit = self._cache.get(key)
        if hit is not None:
            return FetchedPage(**json.loads(hit))
        page = self._inner.fetch(url)
        # Only cache successful fetches; transient 0/5xx should be retried next time.
        if page.ok:
            self._cache.put(key, json.dumps(page.__dict__), kind="fetch")
        return page
