"""Source verifier — the anti-fake-source defense for Proof-First.

A model can *claim* a source; this checks whether the URL is actually reachable and
(optionally) whether the page text plausibly supports the claim. Any source that fails
is discarded. A finding that loses all of its sources is downgraded to LOW — so the
agent can never present a MEDIUM/HIGH claim backed by a hallucinated link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from midas.core.agents.summary import Finding, ProofLevel

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
        page = self._fetcher.fetch(url)
        if not page.ok:
            return SourceCheck(url, reachable=False, supports_claim=None, verified=False)
        if not self._require_support:
            return SourceCheck(url, reachable=True, supports_claim=None, verified=True)

        claim_kw = _keywords(claim)
        if not claim_kw:
            supports = True
        else:
            overlap = len(claim_kw & _keywords(page.text)) / len(claim_kw)
            supports = overlap >= self._min_overlap
        return SourceCheck(url, reachable=True, supports_claim=supports, verified=supports)

    def verify_finding(self, finding: Finding) -> Finding:
        """Keep only verified sources; downgrade proof if none survive."""
        checks = (self.check(u, finding.claim) for u in finding.sources)
        verified = [c.url for c in checks if c.verified]
        level = finding.proof_level
        if level.rank >= ProofLevel.MEDIUM.rank and not verified:
            level = ProofLevel.LOW  # claimed evidence didn't hold up → not MED/HIGH
        return Finding(claim=finding.claim, proof_level=level, sources=verified)
