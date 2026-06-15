"""Sprint D2 — Débrouillard research composes search + fetch + verify.

Invariants:
- ≥3 reachable sources → HIGH; 1–2 → MEDIUM; 0 → LOW (downgraded).
- Sources are deduped by canonical URL (fragment-stripped).
- Hallucinated/404 URLs are kept in the source list but flagged unreachable and
  excluded from the verified count — so a HIGH claim is impossible without
  verified evidence.
"""

from __future__ import annotations

from midas.core.agents.summary import ProofLevel
from midas.core.web import (
    SourceVerifier,
    StaticFetcher,
    StaticSearchAdapter,
    research,
)
from midas.core.web.search import SearchHit


def test_three_reachable_sources_yield_high_proof() -> None:
    pages = {
        "https://a.example/p": "content one",
        "https://b.example/p": "content two",
        "https://c.example/p": "content three",
    }
    search = StaticSearchAdapter([
        SearchHit(title=t, url=u) for t, u in [
            ("A", "https://a.example/p"),
            ("B", "https://b.example/p"),
            ("C", "https://c.example/p"),
        ]
    ])
    result = research("topic", search=search, fetcher=StaticFetcher(pages))
    assert result.proof_level == ProofLevel.HIGH
    assert result.verified_count == 3
    assert len(result.sources) == 3
    assert all(s.reachable for s in result.sources)
    assert all(s.content_hash for s in result.sources)


def test_zero_reachable_sources_falls_to_low() -> None:
    search = StaticSearchAdapter([
        SearchHit(title="X", url="https://nope.example/x"),
        SearchHit(title="Y", url="https://nope.example/y"),
    ])
    result = research("topic", search=search, fetcher=StaticFetcher({}))
    assert result.proof_level == ProofLevel.LOW
    assert result.verified_count == 0
    assert any("downgraded" in n.lower() for n in result.notes)


def test_one_or_two_reachable_sources_yield_medium() -> None:
    pages = {"https://a.example/p": "real"}
    search = StaticSearchAdapter([
        SearchHit(title="A", url="https://a.example/p"),
        SearchHit(title="B", url="https://nope.example/b"),
    ])
    result = research("topic", search=search, fetcher=StaticFetcher(pages))
    assert result.proof_level == ProofLevel.MEDIUM
    assert result.verified_count == 1


def test_canonical_url_dedupes_fragment_variants() -> None:
    pages = {"https://a.example/p": "content"}
    search = StaticSearchAdapter([
        SearchHit(title="A", url="https://a.example/p"),
        SearchHit(title="A2", url="https://a.example/p#section-1"),
        SearchHit(title="A3", url="https://a.example/p#section-2"),
    ])
    result = research("topic", search=search, fetcher=StaticFetcher(pages))
    assert len(result.sources) == 1


def test_synthesis_cites_sources_and_marks_unreachable() -> None:
    pages = {"https://a.example/p": "real text"}
    search = StaticSearchAdapter([
        SearchHit(title="Real", url="https://a.example/p"),
        SearchHit(title="Dead", url="https://nope.example/x"),
    ])
    result = research("topic", search=search, fetcher=StaticFetcher(pages))
    assert "[1]" in result.synthesis
    assert "[2]" in result.synthesis
    assert "unreachable" in result.synthesis


def test_unsourced_high_is_impossible_invariant() -> None:
    """The core Proof-First contract: no HIGH without verified evidence."""
    # Empty search results = no sources at all.
    result = research(
        "anything",
        search=StaticSearchAdapter([]),
        fetcher=StaticFetcher({}),
    )
    assert result.proof_level != ProofLevel.HIGH
    assert result.proof_level != ProofLevel.MEDIUM
    assert result.proof_level == ProofLevel.LOW


def test_explicit_verifier_is_honored() -> None:
    pages = {"https://a.example/p": "x"}
    search = StaticSearchAdapter([SearchHit(title="A", url="https://a.example/p")])
    verifier = SourceVerifier(StaticFetcher(pages))
    result = research(
        "q", search=search, fetcher=StaticFetcher(pages), verifier=verifier
    )
    assert result.verified_count == 1
