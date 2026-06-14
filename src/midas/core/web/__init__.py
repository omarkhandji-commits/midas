"""Web — pluggable search + fetch + Proof-First source verification."""

from .cached import CachedFetcher, CachedSearchAdapter
from .fetch import FetchedPage, Fetcher, HttpxFetcher, StaticFetcher
from .search import SearchAdapter, SearchHit, SearxngSearchAdapter, StaticSearchAdapter
from .verify import SourceCheck, SourceVerifier

__all__ = [
    "SearchAdapter",
    "SearchHit",
    "StaticSearchAdapter",
    "SearxngSearchAdapter",
    "Fetcher",
    "FetchedPage",
    "StaticFetcher",
    "HttpxFetcher",
    "SourceVerifier",
    "SourceCheck",
    "CachedSearchAdapter",
    "CachedFetcher",
]
