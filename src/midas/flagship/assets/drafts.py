"""Real business assets: drafts only, never sent.

The Daily Revenue Move should hand the operator usable work, not vague ideas. This
module generates a complete deterministic asset set offline, and can optionally ask
the budgeted router to draft each asset. Every output remains a draft until approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from midas.flagship.opportunity import OpportunityCandidate

ASSET_KEYS = (
    "offer",
    "landing",
    "outreach_email",
    "followup_sequence",
    "seo_brief",
    "content_calendar",
    "call_script",
    "objection_handling",
    "proposal_pdf",
    "invoice_pdf",
    "video_script",
    "action_plan_7d",
)


@dataclass
class AssetSet:
    offer: str
    landing: str
    outreach_email: str
    followup_sequence: str
    seo_brief: str
    content_calendar: str
    call_script: str
    objection_handling: str
    proposal_pdf: str
    invoice_pdf: str
    video_script: str
    action_plan_7d: str

    def as_dict(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in ASSET_KEYS}


def heuristic_assets(c: OpportunityCandidate) -> AssetSet:
    """Produce a deterministic asset set without any LLM. Demo-safe, always works."""
    return AssetSet(
        offer=_heuristic_offer(c),
        landing=_heuristic_landing(c),
        outreach_email=_heuristic_outreach(c),
        followup_sequence=_heuristic_followups(c),
        seo_brief=_heuristic_seo_brief(c),
        content_calendar=_heuristic_content_calendar(c),
        call_script=_heuristic_call_script(c),
        objection_handling=_heuristic_objections(c),
        proposal_pdf=_heuristic_proposal(c),
        invoice_pdf=_heuristic_invoice(c),
        video_script=_heuristic_video_script(c),
        action_plan_7d=_heuristic_action_plan(c),
    )


def _heuristic_offer(c: OpportunityCandidate) -> str:
    return (
        f"# One-page offer - {c.name}\n\n"
        f"**What it is:** {c.summary}\n\n"
        "**Who it's for:** operators experiencing the pain documented in the sources.\n\n"
        "**Promise:** prepare the move; the operator approves and executes. "
        "No revenue is promised.\n\n"
        "**Price:** TBD after demand validation.\n\n"
        f"**Proof so far:** {len(c.findings)} sourced findings."
    )


def _heuristic_landing(c: OpportunityCandidate) -> str:
    sources = ", ".join(c.sources[:3]) if c.sources else "(add sources here)"
    return (
        f"# Landing - {c.name}\n\n"
        f"H1: {c.name} - solve the pain, not the hype.\n\n"
        f"Subhead: {c.summary}\n\n"
        f"Section 1 - The pain: {sources}\n"
        "Section 2 - The focused solution, with approval-default.\n"
        "Section 3 - Why now / why this is lighter than a suite.\n"
        "Section 4 - CTA: 'Review the draft before anything is sent.'\n"
    )


def _heuristic_outreach(c: OpportunityCandidate) -> str:
    return (
        f"Subject: A draft about {c.name} - your eyes only\n\n"
        "Hi {{first_name}},\n\n"
        f"We noticed people in your space hitting this: {c.summary}\n\n"
        "We drafted a focused way to test it. No list-buying, no auto-send: this draft "
        "only leaves your inbox if you approve it.\n\n"
        "Would a 10-minute look be useful?\n\n"
        "- {{operator}}"
    )


def _heuristic_followups(c: OpportunityCandidate) -> str:
    return (
        f"# Follow-up sequence - {c.name}\n\n"
        "Day 0: short value note with one pain signal and one question.\n"
        "Day 3: add one concrete example; no pressure.\n"
        "Day 7: offer a 10-minute teardown or close the loop politely.\n"
        "Rule: every send requires approval and an opt-out path."
    )


def _heuristic_seo_brief(c: OpportunityCandidate) -> str:
    return (
        f"# SEO brief - {c.name}\n\n"
        f"Target keyword: '{c.name.lower()}'.\n"
        "Intent: informational to solution-comparison.\n"
        "Outline:\n"
        "1. The real pain, with sources.\n"
        "2. Why existing tools miss.\n"
        "3. A focused approach.\n"
        "4. How to evaluate without committing.\n"
        "Length: 1200-1600 words. No fake stats."
    )


def _heuristic_content_calendar(c: OpportunityCandidate) -> str:
    return (
        f"# 14-day content calendar - {c.name}\n\n"
        "1. Pain post with one source.\n"
        "2. Before/after workflow.\n"
        "3. Objection post: not a generic AI tool.\n"
        "4. Mini case template.\n"
        "5. Comparison checklist.\n"
        "6. Pricing validation question.\n"
        "7. Demo clip outline.\n"
        "Repeat winners; stop content with no replies."
    )


def _heuristic_call_script(c: OpportunityCandidate) -> str:
    return (
        f"# Call script - {c.name}\n\n"
        "Open: 'I am validating a focused fix for one problem, not selling a suite.'\n"
        f"Pain check: '{c.summary}'\n"
        "Questions: What do you use now? What breaks? What would make this worth trying?\n"
        "Close: ask permission to send a one-page draft. Do not call without consent."
    )


def _heuristic_objections(c: OpportunityCandidate) -> str:
    return (
        f"# Objection handling - {c.name}\n\n"
        "- 'We already have a tool' -> ask which part still takes manual work.\n"
        "- 'No budget' -> offer manual validation before paid work.\n"
        "- 'AI is risky' -> explain approval-default and no automatic sending.\n"
        "- 'Not now' -> ask what trigger would make this urgent."
    )


def _heuristic_proposal(c: OpportunityCandidate) -> str:
    return (
        f"PDF-DRAFT: Proposal - {c.name}\n\n"
        "Scope: validate the pain, prepare one approved asset, track outcome.\n"
        f"Summary: {c.summary}\n"
        f"Evidence: {len(c.findings)} findings; sources: {', '.join(c.sources) or '(none)'}.\n"
        "Terms: draft only until operator approval. No revenue guarantee."
    )


def _heuristic_invoice(c: OpportunityCandidate) -> str:
    return (
        f"PDF-DRAFT: Invoice / Devis - {c.name}\n\n"
        "Line item: Proof-first business asset preparation.\n"
        "Quantity: 1\n"
        "Price: TBD by operator\n"
        "Notes: generated draft; review legal/tax fields before issuing."
    )


def _heuristic_video_script(c: OpportunityCandidate) -> str:
    return (
        f"# 60-second script - {c.name}\n\n"
        "0-5s Hook: the pain in one line.\n"
        "5-25s The sourced signals that say it is real.\n"
        "25-45s The prepared move, drafts visible, approval-gated.\n"
        "45-60s 'Approve to ship, or reject: the agent never decides for you.'"
    )


def _heuristic_action_plan(c: OpportunityCandidate) -> str:
    return (
        f"# 7-day action plan - {c.name}\n\n"
        "Day 1: re-open sources and confirm the pain is current.\n"
        "Day 2: edit the offer and landing draft.\n"
        "Day 3: prepare 10 approved-fit prospects without scraping PII.\n"
        "Day 4: approve or reject the first outreach draft.\n"
        "Day 5: ship one approved asset only.\n"
        "Day 6: record replies/clicks/errors as outcomes.\n"
        "Day 7: keep, change, or kill the move based on evidence."
    )


_PROMPTS = {
    "offer": "Write a one-page offer for {name}. Summary: {summary}. "
    "No hype, no revenue promise. Under 200 words.",
    "landing": "Draft a landing page outline for {name}. Summary: {summary}. "
    "Include H1, subhead, 4 sections, CTA. Under 250 words.",
    "outreach_email": "Draft a short opt-in friendly outreach email about {name}. "
    "Summary: {summary}. Use {{first_name}}. Under 120 words.",
    "followup_sequence": "Draft a 3-message follow-up sequence for {name}. "
    "No pressure tactics. Each send requires approval.",
    "seo_brief": "Write an SEO brief for {name}. Summary: {summary}. "
    "Include keyword, intent, outline, and length target.",
    "content_calendar": "Draft a compact 14-day content calendar for {name}.",
    "call_script": "Draft a short discovery call script for {name}. Include consent language.",
    "objection_handling": "Draft objection handling for {name}. No hype or fake guarantees.",
    "proposal_pdf": "Draft PDF-ready proposal copy for {name}. Summary: {summary}. "
    "Include scope, proof, assumptions, and no-revenue-guarantee language.",
    "invoice_pdf": "Draft PDF-ready invoice/devis copy for {name}. "
    "Include TBD price and review note.",
    "video_script": "Write a 60-second video script for {name}. Summary: {summary}. "
    "Show timestamps. Under 150 words.",
    "action_plan_7d": "Draft a 7-day action plan for {name}: proof, asset, approval, "
    "shipping, outcome tracking.",
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
        "followup_sequence": _heuristic_followups,
        "seo_brief": _heuristic_seo_brief,
        "content_calendar": _heuristic_content_calendar,
        "call_script": _heuristic_call_script,
        "objection_handling": _heuristic_objections,
        "proposal_pdf": _heuristic_proposal,
        "invoice_pdf": _heuristic_invoice,
        "video_script": _heuristic_video_script,
        "action_plan_7d": _heuristic_action_plan,
    }[key](c)
