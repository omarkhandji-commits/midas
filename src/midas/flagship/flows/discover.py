"""Discover — turn a niche into sourced opportunity candidates via the router.

The model is asked to return a strict JSON contract (no prose). We parse + validate
it with Pydantic and enforce Proof-First on the way in:

  - a candidate with no findings is dropped (we don't invent demand);
  - a finding claiming MEDIUM/HIGH proof with no sources is downgraded to LOW
    (the model doesn't get to assert evidence it didn't cite).

This keeps Discover honest no matter what the model emits. The router call is the only
network touch and is fully mockable (inject `complete_fn` on the router in tests).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from midas.core.agents.summary import Finding, ProofLevel
from midas.core.router.router import LLMRouter
from midas.core.web import SearchAdapter, SourceVerifier
from midas.flagship.opportunity import OpportunityCandidate
from midas.flagship.scoring import FactorScores, HardGates

_SCHEMA_HINT = """Return ONLY JSON, no prose. Shape:
{"candidates":[{"name":str,"summary":str,
  "findings":[{"claim":str,"proof_level":"high|medium|low","sources":[str]}],
  "factors":{"demand":0-10,"speed_to_cash":0-10,"mrr_potential":0-10,"low_support":0-10,
    "defensibility":0-10,"low_competition":0-10,"distribution":0-10,"low_cost":0-10,
    "low_launch_time":0-10,"low_risk":0-10,"operator_fit":0-10},
  "gates":{"requires_deception":bool,"legally_gray_or_pii":bool,
    "structurally_high_support":bool,"no_distribution_channel":bool}}]}
Only include a finding's sources if they are real, citable URLs/identifiers. If you
cannot cite a source, mark the finding "low". Do not invent demand."""

DISCOVER_SYSTEM = (
    "You are MIDAS's opportunity scout. Find real, sourced revenue opportunities in a "
    "niche from genuine pain signals (forums, reviews, job boards). " + _SCHEMA_HINT
)


# ── wire models for the JSON contract (validation only; mapped to domain types) ──
class _RawFinding(BaseModel):
    claim: str
    proof_level: ProofLevel = ProofLevel.LOW
    sources: list[str] = Field(default_factory=list)


class _RawCandidate(BaseModel):
    name: str
    summary: str = ""
    findings: list[_RawFinding] = Field(default_factory=list)
    factors: FactorScores | None = None
    gates: HardGates = Field(default_factory=HardGates)


class _RawBatch(BaseModel):
    candidates: list[_RawCandidate] = Field(default_factory=list)


def parse_candidates(text: str) -> list[OpportunityCandidate]:
    """Parse the model's JSON into validated, Proof-First-clamped candidates."""
    try:
        batch = _RawBatch.model_validate_json(_extract_json(text))
    except (ValidationError, ValueError):
        return []

    out: list[OpportunityCandidate] = []
    for rc in batch.candidates:
        findings = [_clamp_finding(rf) for rf in rc.findings]
        if not findings:
            continue  # no evidence → drop, don't invent
        out.append(
            OpportunityCandidate(
                name=rc.name,
                summary=rc.summary,
                findings=findings,
                factors=rc.factors,
                gates=rc.gates,
            )
        )
    return out


def _clamp_finding(rf: _RawFinding) -> Finding:
    # The model doesn't get to claim evidence it didn't cite.
    level = rf.proof_level
    if level.rank >= ProofLevel.MEDIUM.rank and not rf.sources:
        level = ProofLevel.LOW
    return Finding(claim=rf.claim, proof_level=level, sources=list(rf.sources))


def _extract_json(text: str) -> str:
    """Tolerate models that wrap JSON in ```json fences or surrounding prose."""
    s = text.strip()
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def verify_candidates(
    candidates: list[OpportunityCandidate], verifier: SourceVerifier
) -> list[OpportunityCandidate]:
    """Re-check every cited source against the live web; drop now-unsupported candidates.

    Anti-fake-source: a finding's claimed sources are fetched; unreachable/unsupporting
    ones are removed and the finding is downgraded if nothing survives. A candidate left
    with only LOW evidence stays in the list but cannot become the Daily Revenue Move
    (the scan's proof gate handles that) — we don't silently delete, we de-rate.
    """
    out: list[OpportunityCandidate] = []
    for c in candidates:
        c.findings = [verifier.verify_finding(f) for f in c.findings]
        out.append(c)
    return out


def gather_evidence(niche: str, search: SearchAdapter, *, limit: int = 5) -> str:
    """Run a real search and format hits as grounding context for the model."""
    hits = search.search(f"{niche} pain points OR complaints OR pricing", limit=limit)
    if not hits:
        return ""
    lines = ["Real search results to ground your findings (cite these URLs only if relevant):"]
    for h in hits:
        lines.append(f"- {h.title} | {h.url} | {h.snippet}")
    return "\n".join(lines)


def discover_candidates(
    niche: str,
    *,
    router: LLMRouter,
    search: SearchAdapter | None = None,
    verifier: SourceVerifier | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    est_usd: float = 0.0,
    escalate: bool = False,
) -> list[OpportunityCandidate]:
    """Discover candidates in `niche`, parsed + (optionally) source-verified Proof-First.

    If `search` is given, a real search grounds the prompt. If `verifier` is given, every
    cited source is fetched and checked — hallucinated links are stripped and over-claimed
    findings de-rated. Budgeted + receipted via the router.
    """
    grounding = gather_evidence(niche, search) if search is not None else ""
    user = f"Niche: {niche}\n{grounding}\nReturn the JSON now." if grounding else (
        f"Niche: {niche}\nReturn the JSON now."
    )
    messages = [
        {"role": "system", "content": DISCOVER_SYSTEM},
        {"role": "user", "content": user},
    ]
    res = router.complete(
        messages,
        role="cheap",
        escalate=escalate,
        run_id=run_id,
        task_id=task_id,
        est_usd=est_usd,
        agent="scout",
    )
    candidates = parse_candidates(res.text)
    if verifier is not None:
        candidates = verify_candidates(candidates, verifier)
    return candidates
