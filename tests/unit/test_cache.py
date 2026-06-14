"""Research cache: stable keys, TTL expiry, cached search + fetch wrappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from midas.core.cache import ResearchCache, cache_key
from midas.core.web import (
    CachedFetcher,
    CachedSearchAdapter,
    SearchHit,
    StaticFetcher,
    StaticSearchAdapter,
)


def test_key_is_stable_and_distinguishing() -> None:
    assert cache_key("search", "x", 5) == cache_key("search", "x", 5)
    assert cache_key("search", "x", 5) != cache_key("search", "x", 6)
    assert cache_key("search", "x") != cache_key("fetch", "x")


def test_put_get_evict(tmp_path: Path) -> None:
    c = ResearchCache(tmp_path / "c.db")
    c.put("k1", "value-1", kind="search")
    assert c.get("k1") == "value-1"
    c.evict("k1")
    assert c.get("k1") is None


def test_ttl_expiry(tmp_path: Path) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    c = ResearchCache(tmp_path / "c.db", default_ttl=timedelta(hours=1), clock=lambda: now[0])
    c.put("k", "v")
    assert c.get("k") == "v"
    now[0] += timedelta(hours=2)  # past TTL
    assert c.get("k") is None  # stale evidence is not served


# ── decorators reuse the network result on the second call ────────────────────
def test_cached_search_hits_on_second_call(tmp_path: Path) -> None:
    calls = []

    class _Counter(StaticSearchAdapter):
        def search(self, q, *, limit=5):
            calls.append(q)
            return super().search(q, limit=limit)

    inner = _Counter([SearchHit("t", "https://x/1", "snip")])
    c = ResearchCache(tmp_path / "c.db")
    a = CachedSearchAdapter(inner, c)
    a.search("plumbers")
    a.search("plumbers")
    assert len(calls) == 1  # second call served from cache


def test_cached_fetcher_skips_network_on_hit(tmp_path: Path) -> None:
    calls = []

    class _CountingFetcher(StaticFetcher):
        def fetch(self, url):
            calls.append(url)
            return super().fetch(url)

    inner = _CountingFetcher({"https://x/1": "ok-content"})
    c = ResearchCache(tmp_path / "c.db")
    f = CachedFetcher(inner, c)
    f.fetch("https://x/1")
    p = f.fetch("https://x/1")
    assert p.text == "ok-content"
    assert len(calls) == 1


def test_cached_fetcher_does_not_cache_failures(tmp_path: Path) -> None:
    # Don't poison the cache with 404s — let next time retry the network.
    inner = StaticFetcher({})
    c = ResearchCache(tmp_path / "c.db")
    f = CachedFetcher(inner, c)
    f.fetch("https://nope/x")
    assert c.stats() == {}  # nothing was stored
