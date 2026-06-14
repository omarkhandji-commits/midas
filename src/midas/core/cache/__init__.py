"""Cache — durable research/fetch/summary cache to keep token spend honest."""

from .research import ResearchCache, cache_key

__all__ = ["ResearchCache", "cache_key"]
