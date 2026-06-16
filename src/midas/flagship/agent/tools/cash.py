"""Cash-oriented artifact factory — landings, products, outreach, proposals, ads.

Same contract as :mod:`midas.flagship.agent.tools.artifact`:

- Each ``plan_*`` builds the approval payload (no write); bytes live in the plan,
  ``sha256_new`` lets the reviewer verify the exact content before approval.
- Each ``build_*_content`` is deterministic so the post-approval executor
  rebuilds the same bytes from the payload.
- All tools are APPROVE-tier (registered under ``repo_write``).
- No egress, no private access, no embedded scripts. Pure text/HTML/Markdown.

The point is not to write fancy copy — it's to give the planner a vocabulary
of *cash-shaped* artifacts so it stops falling back to "artifact.text" for
work that has a clear business shape.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .artifact import ArtifactPlan
from .fsguard import FsGuard


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_prev(target_path: str) -> str | None:
    from pathlib import Path

    p = Path(target_path)
    if not p.exists() or not p.is_file():
        return None
    return _sha256(p.read_bytes())


def _make_plan(
    *, kind: str, target_path: str, content: str, preview: str, meta: dict[str, Any]
) -> ArtifactPlan:
    data = content.encode("utf-8")
    return ArtifactPlan(
        kind=kind,  # type: ignore[arg-type]
        path=target_path,
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target_path),
        preview=preview[:400],
        meta=meta,
    )


# ── landing page (self-contained HTML, no remote scripts) ────────────────────


def build_landing_content(
    *, headline: str, subheading: str, body: str, cta_text: str, cta_href: str = "#"
) -> str:
    """Self-contained HTML — no remote script tags, no analytics calls."""
    if not headline.strip():
        raise ValueError("landing.draft needs a non-empty headline")
    if not cta_text.strip():
        raise ValueError("landing.draft needs a non-empty cta_text")
    # Minimal escape — these strings end up in HTML.
    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    css = (  # noqa: E501 - inline CSS string; the file is self-contained on purpose
        "body{font-family:system-ui,sans-serif;max-width:720px;margin:3rem auto;"
        "padding:0 1rem;line-height:1.5;color:#111}"
        "h1{font-size:2.25rem;margin-bottom:.5rem}"
        "h2{font-weight:400;color:#444;margin-top:0}"
        "a.cta{display:inline-block;background:#111;color:#fff;"
        "padding:.85rem 1.4rem;border-radius:6px;text-decoration:none;margin-top:1.5rem}"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        f"<title>{esc(headline)}</title>"
        f"<style>{css}</style></head><body>"
        f"<h1>{esc(headline)}</h1>"
        f"<h2>{esc(subheading)}</h2>"
        f"<div>{esc(body)}</div>"
        f'<a class="cta" href="{esc(cta_href)}">{esc(cta_text)}</a>'
        "</body></html>\n"
    )


def plan_landing(
    guard: FsGuard,
    path: str,
    *,
    headline: str,
    subheading: str = "",
    body: str = "",
    cta_text: str,
    cta_href: str = "#",
) -> ArtifactPlan:
    target = guard.resolve(path)
    html = build_landing_content(
        headline=headline,
        subheading=subheading,
        body=body,
        cta_text=cta_text,
        cta_href=cta_href,
    )
    return _make_plan(
        kind="html",
        target_path=str(target),
        content=html,
        preview=f"{headline}\n{subheading}\n\n[CTA: {cta_text}]",
        meta={"headline": headline, "cta_text": cta_text, "cta_href": cta_href},
    )


# ── digital product (Markdown brief + structure) ─────────────────────────────


def build_product_content(
    *, title: str, audience: str, problem: str, deliverables: list[str], price_usd: float
) -> str:
    if not title.strip():
        raise ValueError("product.draft needs a non-empty title")
    if not deliverables:
        raise ValueError("product.draft needs at least one deliverable")
    delivs = "\n".join(f"- {d}" for d in deliverables)
    return (
        f"# {title}\n\n"
        f"**Audience.** {audience}\n\n"
        f"**Problem it solves.** {problem}\n\n"
        f"**Price.** ${price_usd:.2f} USD\n\n"
        f"## Deliverables\n{delivs}\n\n"
        "## Honest disclaimer\n"
        "This is a draft outline, not a sales claim. No revenue is promised.\n"
    )


def plan_product(
    guard: FsGuard,
    path: str,
    *,
    title: str,
    audience: str = "",
    problem: str = "",
    deliverables: list[str],
    price_usd: float = 0.0,
) -> ArtifactPlan:
    target = guard.resolve(path)
    md = build_product_content(
        title=title,
        audience=audience,
        problem=problem,
        deliverables=deliverables,
        price_usd=float(price_usd),
    )
    return _make_plan(
        kind="markdown",
        target_path=str(target),
        content=md,
        preview=f"{title} (${price_usd:.2f})\n\n{problem}",
        meta={"title": title, "price_usd": float(price_usd), "n_deliverables": len(deliverables)},
    )


# ── outreach sequence (Markdown plan with N steps) ───────────────────────────


def build_outreach_content(
    *, audience: str, offer: str, steps: list[dict[str, str]]
) -> str:
    if not audience.strip() or not offer.strip():
        raise ValueError("outreach.sequence needs non-empty audience and offer")
    if not steps:
        raise ValueError("outreach.sequence needs at least one step")
    lines: list[str] = [
        "# Outreach sequence",
        "",
        f"**Audience.** {audience}",
        f"**Offer.** {offer}",
        "",
        "## Steps",
    ]
    for i, st in enumerate(steps, start=1):
        channel = str(st.get("channel") or "email")
        delay = str(st.get("delay") or ("day 0" if i == 1 else f"+{i - 1}d"))
        subject = str(st.get("subject") or "")
        body = str(st.get("body") or "")
        lines.append(f"### Step {i} — {channel} ({delay})")
        if subject:
            lines.append(f"Subject: {subject}")
        lines.append("")
        lines.append(body or "(draft body)")
        lines.append("")
    lines.append("---")
    lines.append("Sending is gated. This file is a draft plan; no message is sent until approval.")
    return "\n".join(lines) + "\n"


def plan_outreach_sequence(
    guard: FsGuard,
    path: str,
    *,
    audience: str,
    offer: str,
    steps: list[dict[str, str]],
) -> ArtifactPlan:
    target = guard.resolve(path)
    md = build_outreach_content(audience=audience, offer=offer, steps=steps)
    return _make_plan(
        kind="markdown",
        target_path=str(target),
        content=md,
        preview=f"Sequence: {len(steps)} steps for {audience}",
        meta={"audience": audience, "offer": offer, "n_steps": len(steps)},
    )


# ── proposal (Markdown — turned into PDF only on demand via pdf.draft) ───────


def build_proposal_content(
    *,
    client: str,
    project: str,
    scope: list[str],
    price_usd: float,
    timeline: str = "",
    currency: str = "USD",
) -> str:
    if not client.strip() or not project.strip():
        raise ValueError("proposal.draft needs non-empty client and project")
    if not scope:
        raise ValueError("proposal.draft needs at least one scope item")
    scope_md = "\n".join(f"- {s}" for s in scope)
    return (
        f"# Proposal — {project}\n\n"
        f"**Client.** {client}\n\n"
        f"## Scope\n{scope_md}\n\n"
        f"## Price\n{price_usd:.2f} {currency}\n\n"
        f"## Timeline\n{timeline or 'to be agreed'}\n\n"
        "## Notes\n"
        "This proposal is a draft. Pricing assumes the scope above; changes are re-quoted.\n"
    )


def plan_proposal(
    guard: FsGuard,
    path: str,
    *,
    client: str,
    project: str,
    scope: list[str],
    price_usd: float,
    timeline: str = "",
    currency: str = "USD",
) -> ArtifactPlan:
    target = guard.resolve(path)
    md = build_proposal_content(
        client=client,
        project=project,
        scope=scope,
        price_usd=float(price_usd),
        timeline=timeline,
        currency=currency,
    )
    return _make_plan(
        kind="markdown",
        target_path=str(target),
        content=md,
        preview=f"Proposal for {client}: {project} — {price_usd:.2f} {currency}",
        meta={
            "client": client,
            "project": project,
            "price_usd": float(price_usd),
            "currency": currency,
        },
    )


# ── quote (compact variant of proposal — line items + total) ─────────────────


def build_quote_content(
    *,
    client: str,
    items: list[tuple[str, float, float]],
    currency: str = "USD",
    quote_number: str = "",
    notes: str = "",
) -> str:
    if not client.strip():
        raise ValueError("quote.draft needs non-empty client")
    if not items:
        raise ValueError("quote.draft needs at least one line item")
    lines: list[str] = [
        f"# Quote {quote_number}".rstrip(),
        "",
        f"**Client.** {client}",
        "",
        "## Items",
    ]
    total = 0.0
    for entry in items:
        label, qty, unit = entry[0], float(entry[1]), float(entry[2])
        amount = qty * unit
        total += amount
        lines.append(f"- {label} — {qty} × {unit:.2f} = {amount:.2f} {currency}")
    lines.append("")
    lines.append(f"**Total.** {total:.2f} {currency}")
    if notes.strip():
        lines.append("")
        lines.append(f"_Notes._ {notes.strip()}")
    return "\n".join(lines) + "\n"


def plan_quote(
    guard: FsGuard,
    path: str,
    *,
    client: str,
    items: list[tuple[str, float, float]],
    currency: str = "USD",
    quote_number: str = "",
    notes: str = "",
) -> ArtifactPlan:
    target = guard.resolve(path)
    md = build_quote_content(
        client=client, items=items, currency=currency, quote_number=quote_number, notes=notes,
    )
    return _make_plan(
        kind="markdown",
        target_path=str(target),
        content=md,
        preview=f"Quote {quote_number} — {client} ({len(items)} items)",
        meta={"client": client, "currency": currency, "n_items": len(items)},
    )


# ── ad copy (Markdown variants — text only, gated) ───────────────────────────


def build_adcopy_content(
    *, product: str, audience: str, variants: list[dict[str, str]]
) -> str:
    if not product.strip() or not audience.strip():
        raise ValueError("adcopy.draft needs non-empty product and audience")
    if not variants:
        raise ValueError("adcopy.draft needs at least one variant")
    lines: list[str] = [
        f"# Ad copy — {product}",
        "",
        f"**Audience.** {audience}",
        "",
        "## Variants",
    ]
    for i, v in enumerate(variants, start=1):
        headline = str(v.get("headline") or "").strip()
        body = str(v.get("body") or "").strip()
        cta = str(v.get("cta") or "").strip()
        lines.append(f"### Variant {i}")
        if headline:
            lines.append(f"- Headline: {headline}")
        if body:
            lines.append(f"- Body: {body}")
        if cta:
            lines.append(f"- CTA: {cta}")
        lines.append("")
    lines.append("---")
    lines.append("Publishing is gated. Variants here are drafts only.")
    return "\n".join(lines) + "\n"


def plan_adcopy(
    guard: FsGuard,
    path: str,
    *,
    product: str,
    audience: str,
    variants: list[dict[str, str]],
) -> ArtifactPlan:
    target = guard.resolve(path)
    md = build_adcopy_content(product=product, audience=audience, variants=variants)
    return _make_plan(
        kind="markdown",
        target_path=str(target),
        content=md,
        preview=f"Ad copy: {product} — {len(variants)} variants",
        meta={"product": product, "audience": audience, "n_variants": len(variants)},
    )


# ── post-approval executors (rebuild bytes deterministically) ────────────────


def execute_landing(payload: dict[str, Any]) -> str:
    return build_landing_content(
        headline=str(payload.get("headline") or ""),
        subheading=str(payload.get("subheading") or ""),
        body=str(payload.get("body") or ""),
        cta_text=str(payload.get("cta_text") or ""),
        cta_href=str(payload.get("cta_href") or "#"),
    )


def execute_product(payload: dict[str, Any]) -> str:
    return build_product_content(
        title=str(payload.get("title") or ""),
        audience=str(payload.get("audience") or ""),
        problem=str(payload.get("problem") or ""),
        deliverables=list(payload.get("deliverables") or []),
        price_usd=float(payload.get("price_usd") or 0.0),
    )


def execute_outreach(payload: dict[str, Any]) -> str:
    return build_outreach_content(
        audience=str(payload.get("audience") or ""),
        offer=str(payload.get("offer") or ""),
        steps=list(payload.get("steps") or []),
    )


def execute_proposal(payload: dict[str, Any]) -> str:
    return build_proposal_content(
        client=str(payload.get("client") or ""),
        project=str(payload.get("project") or ""),
        scope=list(payload.get("scope") or []),
        price_usd=float(payload.get("price_usd") or 0.0),
        timeline=str(payload.get("timeline") or ""),
        currency=str(payload.get("currency") or "USD"),
    )


def execute_quote(payload: dict[str, Any]) -> str:
    return build_quote_content(
        client=str(payload.get("client") or ""),
        items=[(str(e[0]), float(e[1]), float(e[2])) for e in (payload.get("items") or [])],
        currency=str(payload.get("currency") or "USD"),
        quote_number=str(payload.get("quote_number") or ""),
        notes=str(payload.get("notes") or ""),
    )


def execute_adcopy(payload: dict[str, Any]) -> str:
    return build_adcopy_content(
        product=str(payload.get("product") or ""),
        audience=str(payload.get("audience") or ""),
        variants=list(payload.get("variants") or []),
    )
