"""Context economy primitives.

The compressor is deliberately proof-safe: it may shorten working context, but it
keeps an addressable original for any chunk it compresses so later decisions can
re-read the raw evidence instead of trusting a lossy summary.
"""

from .budget import ContextBudget, ContextChunk, RunMode, SafeContextCompressor

__all__ = ["ContextBudget", "ContextChunk", "RunMode", "SafeContextCompressor"]
