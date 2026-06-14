"""Token-economy layer with a hard proof-safety invariant.

The rule is simple: MIDAS may compress context to spend fewer tokens, but any
compressed chunk must keep a stable hash and an in-process original. Decisions that
matter can call `retrieve_original()` before citing or acting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from midas.core.receipts.models import sha256_hex

RunMode = Literal["fast", "deep", "war-room"]


@dataclass(frozen=True)
class ContextBudget:
    mode: RunMode = "deep"
    max_chars_per_chunk: int = 4_000
    max_chunks: int = 24
    preserve_originals: bool = True

    @classmethod
    def for_mode(cls, mode: RunMode) -> ContextBudget:
        if mode == "fast":
            return cls(mode=mode, max_chars_per_chunk=1_800, max_chunks=10)
        if mode == "war-room":
            return cls(mode=mode, max_chars_per_chunk=8_000, max_chunks=48)
        return cls(mode=mode, max_chars_per_chunk=4_000, max_chunks=24)


@dataclass(frozen=True)
class ContextChunk:
    label: str
    text: str
    original_hash: str
    compressed: bool
    original_chars: int
    compressed_chars: int

    @property
    def saved_chars(self) -> int:
        return max(0, self.original_chars - self.compressed_chars)


class SafeContextCompressor:
    """Lossy working-context compression with reversible originals."""

    def __init__(self, budget: ContextBudget | None = None) -> None:
        self.budget = budget or ContextBudget()
        self._originals: dict[str, str] = {}

    def compress(self, label: str, text: str, *, proof_critical: bool = False) -> ContextChunk:
        original = text or ""
        h = sha256_hex(original.encode("utf-8"))
        if self.budget.preserve_originals:
            self._originals[h] = original

        if proof_critical or len(original) <= self.budget.max_chars_per_chunk:
            return ContextChunk(
                label=label,
                text=original,
                original_hash=h,
                compressed=False,
                original_chars=len(original),
                compressed_chars=len(original),
            )

        summary = self._lossy_summary(original, self.budget.max_chars_per_chunk)
        wrapped = (
            f"[compressed-context label={label!r} original_sha256={h} "
            f"original_chars={len(original)}]\n{summary}"
        )
        return ContextChunk(
            label=label,
            text=wrapped,
            original_hash=h,
            compressed=True,
            original_chars=len(original),
            compressed_chars=len(wrapped),
        )

    def retrieve_original(self, original_hash: str) -> str | None:
        return self._originals.get(original_hash)

    @staticmethod
    def _lossy_summary(text: str, max_chars: int) -> str:
        if max_chars < 800:
            max_chars = 800
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        head = "\n".join(sentences[:4]) if sentences else text[: max_chars // 3]
        tail = "\n".join(sentences[-3:]) if len(sentences) > 4 else text[-max_chars // 4 :]
        keywords = _top_keywords(text, limit=16)
        budget = max_chars - len(head) - len(tail) - 160
        middle = text[len(text) // 2 : len(text) // 2 + max(0, budget // 2)].strip()
        return (
            f"Key terms: {', '.join(keywords) or '(none)'}\n"
            f"Opening:\n{head}\n\n"
            f"Middle sample:\n{middle}\n\n"
            f"Ending:\n{tail}"
        )[:max_chars]


def _top_keywords(text: str, *, limit: int) -> list[str]:
    stop = {
        "the", "and", "for", "that", "with", "this", "from", "you", "your", "are",
        "was", "were", "have", "has", "not", "but", "can", "will", "they", "their",
    }
    counts: dict[str, int] = {}
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower()):
        if word in stop:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]
