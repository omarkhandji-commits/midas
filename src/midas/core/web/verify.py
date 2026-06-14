"""Source verifier — the anti-fake-source defense for Proof-First.

A model can *claim* a source; this checks whether the URL is actually reachable and
(optionally) whether the page text plausibly supports the claim. Any source that fails
is discarded. A finding that loses all of its sources is downgraded to LOW — so the
agent can never present a MEDIUM/HIGH claim backed by a hallucinated link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urldefrag

from midas.core.agents.summary import Finding, ProofLevel
from midas.core.receipts.models import sha256_hex, utcnow_iso

from .fetch import Fetcher

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are", "was",
    "were", "with", "that", "this", "it", "as", "at", "by", "be", "no", "not",
}


@dataclass
class SourceCheck:
    url: str
    reachable: bool
    supports_claim: bool | None  # None when support-checking is disabled
    verified: bool
    canonical_url: str = ""
    content_hash: str = ""
    checked_ts: str = ""
    quote: str = ""
    support_score: float = 0.0
    freshness_score: float = 0.5
    contradiction: str | None = None
    suggested_level: ProofLevel = ProofLevel.LOW


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


class SourceVerifier:
    def __init__(
        self,
        fetcher: Fetcher,
        *,
        require_support: bool = False,
        min_overlap: float = 0.25,
    ) -> None:
        self._fetcher = fetcher
        self._require_support = require_support
        self._min_overlap = min_overlap

    def check(self, url: str, claim: str) -> SourceCheck:
        canonical = _canonical_url(url)
        checked_ts = utcnow_iso()
        page = self._fetcher.fetch(url)
        if not page.ok:
            return SourceCheck(
                url=url,
                canonical_url=canonical,
                reachable=False,
                supports_claim=None,
                verified=False,
                checked_ts=checked_ts,
                contradiction="source unreachable",
            )
        content_hash = sha256_hex(page.text.encode("utf-8"))
        quote = _best_quote(page.text, claim)
        if not self._require_support:
            return SourceCheck(
                url=url,
                canonical_url=canonical,
                reachable=True,
                supports_claim=None,
                verified=True,
                checked_ts=checked_ts,
                content_hash=content_hash,
                quote=quote,
                support_score=0.5,
                suggested_level=ProofLevel.MEDIUM,
            )

        claim_kw = _keywords(claim)
        if not claim_kw:
            supports = True
            overlap = 1.0
        else:
            overlap = len(claim_kw & _keywords(page.text)) / len(claim_kw)
            supports = overlap >= self._min_overlap
        contradiction = None if supports else "lexical support below threshold"
        return SourceCheck(
            url=url,
            canonical_url=canonical,
            reachable=True,
            supports_claim=supports,
            verified=supports,
            checked_ts=checked_ts,
            content_hash=content_hash,
            quote=quote,
            support_score=round(overlap, 4),
            contradiction=contradiction,
            suggested_level=_suggest_level(overlap),
        )

    def verify_finding(self, finding: Finding) -> Finding:
        """Keep only verified sources; downgrade proof if none survive."""
        checks = (self.check(u, finding.claim) for u in finding.sources)
        verified = [c.url for c in checks if c.verified]
        level = finding.proof_level
        if level.rank >= ProofLevel.MEDIUM.rank and not verified:
            level = ProofLevel.LOW  # claimed evidence didn't hold up → not MED/HIGH
        return Finding(claim=finding.claim, proof_level=level, sources=verified)

    def evidence_pack(self, finding: Finding) -> list[SourceCheck]:
        """Return full source diagnostics for UI/evals without mutating the finding."""
        return [self.check(u, finding.claim) for u in finding.sources]


def _canonical_url(url: str) -> str:
    return urldefrag(url.strip())[0]


def _best_quote(text: str, claim: str, *, limit: int = 220) -> str:
    claim_kw = _keywords(claim)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return " ".join(text.split())[:limit]
    ranked = sorted(
        sentences,
        key=lambda s: len(claim_kw & _keywords(s)),
        reverse=True,
    )
    return " ".join(ranked[0].split())[:limit]


def _suggest_level(overlap: float) -> ProofLevel:
    if overlap >= 0.75:
        return ProofLevel.HIGH
    if overlap >= 0.25:
        return ProofLevel.MEDIUM
    return ProofLevel.LOW
