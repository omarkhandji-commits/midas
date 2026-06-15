"""Débrouillard web research — composes existing primitives, never reinvents them.

`research(query, ...)` runs the search → fetch → verify → synthesize loop and
returns a `ResearchResult` carrying every cited URL's verification status,
content hash, best quote, and computed proof level. The proof contract is the
same as the rest of MIDAS: **no HIGH without at least one verified source**.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from midas.core.agents.summary import ProofLevel
from midas.core.receipts.models import utcnow_iso

from .fetch import Fetcher
from .search import SearchAdapter, SearchHit
from .verify import SourceCheck, SourceVerifier


@dataclass
class ResearchSource:
    url: str
    title: str
    snippet: str
    reachable: bool
    content_hash: str
    quote: str
    support_score: float
    proof_level: ProofLevel
    canonical_url: str = ""


@dataclass
class ResearchResult:
    query: str
    ts: str
    sources: list[ResearchSource]
    proof_level: ProofLevel
    synthesis: str
    notes: list[str] = field(default_factory=list)

    @property
    def verified_count(self) -> int:
        return sum(1 for s in self.sources if s.reachable)

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["proof_level"] = self.proof_level.value
        for src in out["sources"]:
            src["proof_level"] = src["proof_level"].value if hasattr(
                src["proof_level"], "value"
            ) else src["proof_level"]
        return out


def research(
    query: str,
    *,
    search: SearchAdapter,
    fetcher: Fetcher,
    verifier: SourceVerifier | None = None,
    k: int = 5,
) -> ResearchResult:
    """Best-effort multi-source research with Proof-First downgrading.

    - `search.search(query, limit=k)` grounds the answer in real hits (no model URLs).
    - Each hit is fetched + verified (if a verifier is provided).
    - Sources that don't return 2xx with non-empty content are kept as `reachable=False`
      and excluded from the verified count.
    - Final proof level: HIGH if ≥3 verified, MEDIUM if 1–2, LOW if 0.
    """
    verifier = verifier or SourceVerifier(fetcher)
    hits: list[SearchHit] = list(search.search(query, limit=k))
    sources = [_build_source(verifier.check(hit.url, query), hit) for hit in hits]
    sources = _dedupe_by_canonical(sources)
    proof_level = _compute_overall_level(sources)
    notes: list[str] = []
    if proof_level == ProofLevel.LOW:
        notes.append("No reachable source: proof level downgraded to LOW.")
    return ResearchResult(
        query=query,
        ts=utcnow_iso(),
        sources=sources,
        proof_level=proof_level,
        synthesis=_synthesize(query, sources),
        notes=notes,
    )


def _build_source(check: SourceCheck, hit: SearchHit) -> ResearchSource:
    return ResearchSource(
        url=hit.url,
        title=hit.title,
        snippet=hit.snippet,
        reachable=check.reachable,
        content_hash=check.content_hash,
        quote=check.quote,
        support_score=check.support_score,
        proof_level=check.suggested_level if check.reachable else ProofLevel.LOW,
        canonical_url=check.canonical_url,
    )


def _dedupe_by_canonical(sources: Iterable[ResearchSource]) -> list[ResearchSource]:
    seen: set[str] = set()
    out: list[ResearchSource] = []
    for src in sources:
        key = src.canonical_url or src.url
        if key in seen:
            continue
        seen.add(key)
        out.append(src)
    return out


def _compute_overall_level(sources: list[ResearchSource]) -> ProofLevel:
    verified = sum(1 for s in sources if s.reachable)
    if verified >= 3:
        return ProofLevel.HIGH
    if verified >= 1:
        return ProofLevel.MEDIUM
    return ProofLevel.LOW


def _synthesize(query: str, sources: list[ResearchSource]) -> str:
    """Markdown synthesis with numbered [n] citations.

    Deliberately simple — the agent layer may rewrite this with an LLM later. The
    bytes that survive into the receipt are the cited URLs + content hashes, not
    the synthesis prose, so the synthesis is allowed to be plain.
    """
    if not sources:
        return f"No sources found for: {query}\n"
    lines = [f"# Research: {query}", ""]
    for i, src in enumerate(sources, start=1):
        status = "" if src.reachable else " *(unreachable)*"
        quote = src.quote.strip() or src.snippet.strip()
        lines.append(f"**[{i}]** {src.title}{status} — {src.url}")
        if quote:
            lines.append(f"> {quote}")
        lines.append("")
    return "\n".join(lines)
