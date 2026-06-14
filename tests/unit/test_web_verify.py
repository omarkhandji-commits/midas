"""Web layer: source verification (anti-fake-source) + search-grounded, verified discover."""

from __future__ import annotations

import json

from midas.core.agents.summary import Finding, ProofLevel
from midas.core.config.models import ProvidersConfig, RoleConfig
from midas.core.router import ChatResult, LLMRouter
from midas.core.web import SearchHit, SourceVerifier, StaticFetcher, StaticSearchAdapter
from midas.flagship.flows import discover_candidates, gather_evidence, verify_candidates
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores

_FACTORS = FactorScores(
    demand=9, speed_to_cash=8, mrr_potential=9, low_support=8, defensibility=6,
    low_competition=7, distribution=8, low_cost=9, low_launch_time=8, low_risk=8, operator_fit=8,
)


# ── verifier: anti-fake-source ───────────────────────────────────────────────
def test_unreachable_source_is_discarded_and_downgrades() -> None:
    fetcher = StaticFetcher({})  # every URL 404s
    v = SourceVerifier(fetcher)
    f = Finding("rivals raised prices", ProofLevel.HIGH, sources=["https://made-up.example/x"])
    out = v.verify_finding(f)
    assert out.sources == []  # fake link stripped
    assert out.proof_level == ProofLevel.LOW  # over-claim de-rated


def test_reachable_source_keeps_proof() -> None:
    fetcher = StaticFetcher({"https://real.example/p": "lots of real content here"})
    v = SourceVerifier(fetcher)
    f = Finding("a sourced claim", ProofLevel.HIGH, sources=["https://real.example/p"])
    out = v.verify_finding(f)
    assert out.sources == ["https://real.example/p"]
    assert out.proof_level == ProofLevel.HIGH


def test_support_check_rejects_irrelevant_page() -> None:
    fetcher = StaticFetcher({"https://real.example/p": "a page about unrelated gardening tips"})
    v = SourceVerifier(fetcher, require_support=True)
    f = Finding(
        "plumbers complain about unpaid invoices and chasing clients",
        ProofLevel.HIGH,
        sources=["https://real.example/p"],
    )
    out = v.verify_finding(f)
    assert out.sources == []  # reachable but does not support the claim
    assert out.proof_level == ProofLevel.LOW


# ── search grounding ─────────────────────────────────────────────────────────
def test_gather_evidence_formats_real_hits() -> None:
    search = StaticSearchAdapter([SearchHit("Plumbers hate invoicing", "https://r.x/1", "snippet")])
    ctx = gather_evidence("plumbing tools", search)
    assert "https://r.x/1" in ctx and "Plumbers hate invoicing" in ctx


# ── wired discover with search + verify ──────────────────────────────────────
def _router(text: str) -> LLMRouter:
    providers = ProvidersConfig(
        roles={"cheap": RoleConfig(primary="m"), "smart": RoleConfig(primary="s")}
    )
    return LLMRouter(
        providers,
        complete_fn=lambda model, msgs: ChatResult(
            text=text, model=model, prompt_tokens=10, completion_tokens=5
        ),
    )


def _payload(source: str) -> str:
    return json.dumps(
        {
            "candidates": [
                {
                    "name": "Invoice chaser",
                    "summary": "follow-ups",
                    "findings": [
                        {"claim": "real pain", "proof_level": "high", "sources": [source]}
                    ],
                    "factors": _FACTORS.model_dump(),
                    "gates": {},
                }
            ]
        }
    )


def test_discover_verifies_model_cited_sources() -> None:
    # Model cites a real URL → survives verification at HIGH.
    fetcher = StaticFetcher({"https://real.example/p": "content"})
    v = SourceVerifier(fetcher)
    router = _router(_payload("https://real.example/p"))
    cands = discover_candidates("niche", router=router, verifier=v)
    assert cands[0].proof_level == ProofLevel.HIGH


def test_discover_strips_hallucinated_sources() -> None:
    # Model cites a non-existent URL → stripped, candidate de-rated to LOW.
    fetcher = StaticFetcher({})
    v = SourceVerifier(fetcher)
    router = _router(_payload("https://fake.example/x"))
    cands = discover_candidates("niche", router=router, verifier=v)
    assert cands[0].proof_level == ProofLevel.LOW
    assert cands[0].sources == []


def test_verify_candidates_is_idempotent_on_low() -> None:
    c = OpportunityCandidate(
        name="x", summary="y",
        findings=[Finding("low claim", ProofLevel.LOW)], factors=_FACTORS,
    )
    out = verify_candidates([c], SourceVerifier(StaticFetcher({})))
    assert out[0].findings[0].proof_level == ProofLevel.LOW
