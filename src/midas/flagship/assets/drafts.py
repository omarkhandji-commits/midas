"""Real business assets — drafts only, never sent.

Replaces the empty `draft_assets={}` slot in the Daily Revenue Move with concrete,
operator-ready artifacts: a one-page offer, a landing-page outline, a first outreach
email, an SEO content brief, and a short demo-video script.

Every asset is a **draft**. Approval-default holds: nothing leaves the operator's
machine without their tap. Even with no LLM configured, the heuristic generator
produces usable scaffolds (so the demo works offline).

The optional `router` runs through the same budgeted+receipted path as the rest of
the system, so asset drafting is auditable in cost and content shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from midas.flagship.opportunity import OpportunityCandidate

ASSET_KEYS = ("offer", "landing", "outreach_email", "seo_brief", "video_script")


@dataclass
class AssetSet:
    offer: str
    landing: str
    outreach_email: str
    seo_brief: str
    video_script: str

    def as_dict(self) -> dict[str, str]:
        return {
            "offer": self.offer,
            "landing": self.landing,
            "outreach_email": self.outreach_email,
            "seo_brief": self.seo_brief,
            "video_script": self.video_script,
        }


# ── heuristic drafts (zero-config, deterministic, demo-safe) ─────────────────
def _heuristic_offer(c: OpportunityCandidate) -> str:
    return (
        f"# One-page offer — {c.name}\n\n"
        f"**What it is:** {c.summary}\n\n"
        f"**Who it's for:** operators experiencing the pain documented in our sources.\n\n"
        f"**The promise (concrete, no hype):** prepare the move; the operator approves\n"
        f"and executes. No revenue is promised.\n\n"
        f"**Price (placeholder):** TBD by the operator after validating demand.\n\n"
        f"**Proof so far:** {len(c.findings)} sourced findings."
    )


def _heuristic_landing(c: OpportunityCandidate) -> str:
    return (
        f"# Landing — {c.name}\n\n"
        f"H1: {c.name} — solve the pain, not the hype.\n\n"
        f"Subhead: {c.summary}\n\n"
        f"Section 1 — The pain (cite our sources): "
        + ", ".join(c.sources[:3]) or "(add sources here)" + "\n\n"
        "Section 2 — The solution (drafted, awaiting your edit).\n"
        "Section 3 — Why now / why us.\n"
        "Section 4 — CTA: 'Try it — manual approval per send.'\n"
    )


def _heuristic_outreach(c: OpportunityCandidate) -> str:
    return (
        f"Subject: A draft about {c.name} — your eyes only\n\n"
        "Hi {{first_name}},\n\n"
        f"We noticed people in your space hitting this: {c.summary}\n\n"
        "We drafted a focused tool for it. No spam, no list-buying — this draft only\n"
        "leaves your inbox if you approve the send.\n\n"
        "Would a 10-minute look be useful?\n\n"
        "— {{operator}}"
    )


def _heuristic_seo_brief(c: OpportunityCandidate) -> str:
    return (
        f"# SEO brief — {c.name}\n\n"
        f"Target keyword: '{c.name.lower()}'.\n"
        "Secondary keywords: derive from the pain sources cited.\n"
        "Search intent: informational → solution-comparison.\n"
        "Outline:\n"
        "  1. The real pain (cite sources).\n"
        "  2. Why existing tools miss.\n"
        "  3. A focused approach (the proposed move).\n"
        "  4. How to evaluate it without committing.\n"
        "Length: 1200-1600 words. No outbound links to competitors without context."
    )


def _heuristic_video_script(c: OpportunityCandidate) -> str:
    return (
        f"# 60-second script — {c.name}\n\n"
        "0-5s   Hook: the pain in one line.\n"
        "5-25s  The 3 sourced signals that say it's real.\n"
        "25-45s The prepared move, drafts visible, approval-gated.\n"
        "45-60s 'Approve to ship, or reject — the agent never decides for you.'\n"
    )


def heuristic_assets(c: OpportunityCandidate) -> AssetSet:
    """Produce a deterministic asset set without any LLM. Demo-safe, always works."""
    return AssetSet(
        offer=_heuristic_offer(c),
        landing=_heuristic_landing(c),
        outreach_email=_heuristic_outreach(c),
        seo_brief=_heuristic_seo_brief(c),
        video_script=_heuristic_video_script(c),
    )


# ── LLM-backed drafts (budgeted + receipted via the router) ──────────────────
_PROMPTS = {
    "offer": "Write a one-page offer (markdown) for: {name}. Summary: {summary}. "
             "No hype, no revenue promise. Keep under 200 words.",
    "landing": "Draft a landing page outline (markdown) for: {name}. Summary: {summary}. "
               "Include H1, subhead, 4 sections, and a CTA. Under 250 words.",
    "outreach_email": "Draft a SHORT cold-friendly outreach email about {name}. "
                      "Summary: {summary}. Make it opt-in friendly, no spam patterns. "
                      "Under 120 words. Use {{first_name}} placeholder.",
    "seo_brief": "Write an SEO brief for {name}. Summary: {summary}. Include target keyword, "
                 "intent, outline (5 points), and length target. Under 200 words.",
    "video_script": "Write a 60-second video script for {name}. Summary: {summary}. "
                    "Show timestamps. Under 150 words.",
}


def llm_assets(
    c: OpportunityCandidate,
    *,
    router: Any,
    run_id: str | None = None,
    task_id: str | None = None,
    est_usd_per_asset: float = 0.01,
) -> AssetSet:
    """Generate the asset set via the router. Each call is budgeted + receipted."""
    drafts: dict[str, str] = {}
    for key, template in _PROMPTS.items():
        msg = template.format(name=c.name, summary=c.summary)
        res = router.complete(
            [{"role": "user", "content": msg}],
            role="cheap",
            run_id=run_id,
            task_id=task_id,
            est_usd=est_usd_per_asset,
            agent=f"asset:{key}",
        )
        drafts[key] = res.text.strip() or _heuristic_fallback(key, c)
    return AssetSet(**drafts)


def _heuristic_fallback(key: str, c: OpportunityCandidate) -> str:
    return {
        "offer": _heuristic_offer,
        "landing": _heuristic_landing,
        "outreach_email": _heuristic_outreach,
        "seo_brief": _heuristic_seo_brief,
        "video_script": _heuristic_video_script,
    }[key](c)
