"""Tool registry — wires concrete tool callables into a security-checked Toolset.

Every tool here declares its policy action name. The Sentinel uses that action
to classify the call:
- AUTO actions (read_local_files, build_local_files) execute inline + receipt.
- APPROVE actions (repo_write, execute_code, write_spreadsheet,
  delete_or_overwrite_foreign_file) are queued, never executed inline.

Mutating tools register a *plan* callable (returns a payload dataclass with the
diff/sha256 the approval card will show). The actual write/run happens in a
separate execute step the runtime exposes.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from midas.core.agents.toolset import Tool, Toolset
from midas.core.receipts.models import Taint
from midas.core.sentinel.gate import Sentinel
from midas.core.web import research as web_research
from midas.core.web.fetch import Fetcher
from midas.core.web.search import SearchAdapter
from midas.core.web.verify import SourceVerifier

from .tools.affiliate import generate_affiliate_link
from .tools.artifact import (
    plan_artifact_code,
    plan_artifact_email,
    plan_artifact_invoice,
    plan_artifact_pdf,
    plan_artifact_text,
    plan_artifact_voice,
)
from .tools.blog_seo import lint_blog
from .tools.cash import (
    plan_adcopy,
    plan_landing,
    plan_outreach_sequence,
    plan_product,
    plan_proposal,
    plan_quote,
)
from .tools.code import plan_code_run
from .tools.code_complex import plan_code_complex
from .tools.code_edit import plan_code_edits
from .tools.data_io import csv_read, json_read, plan_csv_write, plan_json_write
from .tools.email_deliverability import check_deliverability
from .tools.email_inbox import read_inbox
from .tools.email_send import plan_email_send
from .tools.fs import fs_list, fs_read, plan_fs_write
from .tools.fsguard import FsGuard
from .tools.http import as_tool_payload as _http_payload
from .tools.http import http_fetch
from .tools.image import plan_image
from .tools.lead import record_leads
from .tools.pdf import pdf_extract
from .tools.repo_map import build_repo_map
from .tools.sheet import plan_sheet_write, sheet_read
from .tools.skill import skill_index, skill_load
from .tools.social import plan_social_publish
from .tools.stripe_pay import plan_payment_link
from .tools.voice_synth import plan_voice_synth
from .tools.web_automate import plan_web_automate
from .tools.web_scrape import _as_tool_payload as _scrape_payload
from .tools.web_scrape import web_scrape


def build_default_toolset(
    *,
    sentinel: Sentinel,
    guard: FsGuard,
    ledger: Any = None,
    approvals: Any = None,
    run_id: str = "",
    search: SearchAdapter | None = None,
    fetcher: Fetcher | None = None,
    verifier: SourceVerifier | None = None,
    skill_registry: Any = None,
    memory_path: str | None = None,
) -> Toolset:
    ts = Toolset(sentinel, ledger=ledger, approvals=approvals, run_id=run_id)

    ts.register(
        Tool(
            name="fs.read",
            action="read_local_files",
            fn=lambda path, max_chars=100_000: _as_dict(fs_read(guard, path, max_chars=max_chars)),
            output_taint=Taint.UNTRUSTED,  # file contents are data, not instructions
        )
    )
    ts.register(
        Tool(
            name="fs.list",
            action="read_local_files",
            fn=lambda path=".": _as_dict(fs_list(guard, path)),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="fs.write",
            action="repo_write",
            # APPROVE-tier: the Toolset will queue this; the planner is NEVER called.
            fn=lambda path, content="": _as_dict(plan_fs_write(guard, path, content)),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="pdf.extract",
            action="read_local_files",
            fn=lambda path, max_chars=100_000: _as_dict(
                pdf_extract(guard, path, max_chars=max_chars)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="sheet.read",
            action="read_local_files",
            fn=lambda path, sheet_name=None, max_rows=5000: _as_dict(
                sheet_read(guard, path, sheet_name=sheet_name, max_rows=max_rows)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="sheet.write",
            action="write_spreadsheet",
            fn=lambda path, cells, sheet_name="Sheet1": _as_dict(
                plan_sheet_write(guard, path, cells=cells, sheet_name=sheet_name)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    # Artifact factory — the débrouillard surface. Every artifact is APPROVE-tier
    # (repo_write); the bytes live in the approval payload until a human resolves.
    ts.register(
        Tool(
            name="artifact.text",
            action="repo_write",
            fn=lambda path, content, kind="text": _as_dict(
                plan_artifact_text(guard, path, content, kind=kind)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="email.draft",
            action="repo_write",
            fn=lambda path, to, subject, body, from_="", cc="": _as_dict(
                plan_artifact_email(
                    guard, path, to=to, subject=subject, body=body, from_=from_, cc=cc
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="pdf.draft",
            action="repo_write",
            fn=lambda path, title, body: _as_dict(
                plan_artifact_pdf(guard, path, title=title, body=body)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="invoice.draft",
            action="repo_write",
            fn=lambda path, to, items, currency="USD", invoice_number="", notes="": _as_dict(
                plan_artifact_invoice(
                    guard, path, to=to, items=items, currency=currency,
                    invoice_number=invoice_number, notes=notes,
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="voice.draft",
            action="repo_write",
            fn=lambda path, text, channel="voice_note": _as_dict(
                plan_artifact_voice(guard, path, text=text, channel=channel)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="code.draft",
            action="repo_write",
            fn=lambda path, content, language="python": _as_dict(
                plan_artifact_code(guard, path, content=content, language=language)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    # Web research — composes search + fetch + verify under the Proof-First contract.
    # AUTO: it does not mutate state; result is UNTRUSTED data the agent can quote.
    if search is not None and fetcher is not None:
        def _do_research(question: str, k: int = 5) -> dict[str, Any]:
            result = web_research(
                question, search=search, fetcher=fetcher, verifier=verifier, k=k,
            )
            return {
                "query": result.query,
                "proof_level": result.proof_level.value,
                "verified_count": result.verified_count,
                "sources": [s.url for s in result.sources],
                "synthesis": result.synthesis,
            }

        ts.register(
            Tool(
                name="research.run",
                action="read_local_files",  # AUTO-tier; verified web reads
                fn=_do_research,
                output_taint=Taint.UNTRUSTED,
            )
        )

    # Structured data — read tools AUTO, write tools gated via fs.write chain.
    ts.register(
        Tool(
            name="json.read",
            action="read_local_files",
            fn=lambda path: _as_dict(json_read(guard, path)),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="json.write",
            action="repo_write",
            fn=lambda path, data, indent=2: _as_dict(
                plan_json_write(guard, path, data, indent=indent)
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="csv.read",
            action="read_local_files",
            fn=lambda path, max_rows=5000: _as_dict(csv_read(guard, path, max_rows=max_rows)),
            output_taint=Taint.UNTRUSTED,
        )
    )
    ts.register(
        Tool(
            name="csv.write",
            action="repo_write",
            fn=lambda path, rows: _as_dict(plan_csv_write(guard, path, rows)),
            output_taint=Taint.TRUSTED,
        )
    )
    # blog.seo_lint — AUTO-tier deterministic SEO checklist on markdown.
    ts.register(
        Tool(
            name="blog.seo_lint",
            action="read_local_files",
            fn=lambda markdown, title="", meta_description="", site_domain="": (
                lint_blog(
                    markdown=markdown,
                    title=title,
                    meta_description=meta_description,
                    site_domain=site_domain,
                ).to_dict()
            ),
            output_taint=Taint.TRUSTED,
        )
    )

    # code.edit_plan — APPROVE-tier multi-file search/replace.
    # All-or-nothing exact-match. Operator sees per-file LOC delta + sha256
    # of intent. Rebuilt at execute time to refuse drift.
    ts.register(
        Tool(
            name="code.edit_plan",
            action="repo_write",
            fn=lambda edits: _as_dict(plan_code_edits(guard, edits=edits)),
            output_taint=Taint.TRUSTED,
        )
    )

    # code.repo_map — AUTO-tier AST walk + import-graph ranking.
    # Foundation of the Phase 6 native coder: feeds the planner a ranked
    # list of which files matter most without dumping the whole repo.
    def _repo_map_payload(subdir: str = ".", top: int = 20) -> dict[str, Any]:
        rmap = build_repo_map(guard, subdir=subdir)
        return {
            **rmap.as_dict(),
            "top": [f.to_dict() for f in rmap.top(n=int(top))],
        }
    ts.register(
        Tool(
            name="code.repo_map",
            action="read_local_files",
            fn=_repo_map_payload,
            output_taint=Taint.TRUSTED,
        )
    )

    # lead.record — AUTO-tier CRM bridge from inbox → MemoryKind.RESULT.
    # Idempotent on (from_addr, uid); writes only when an intent word matches.
    if memory_path is not None:
        _mem_path = memory_path
        ts.register(
            Tool(
                name="lead.record",
                action="read_local_files",
                fn=lambda messages: record_leads(
                    messages=messages,
                    store_path=_mem_path,
                ).as_dict(),
                output_taint=Taint.TRUSTED,
            )
        )

    # affiliate.link.generate — AUTO-tier pure URL builder. No egress.
    ts.register(
        Tool(
            name="affiliate.link.generate",
            action="read_local_files",
            fn=lambda merchant_url, campaign, source="midas", medium="referral",
            content="", term="", extra_params=None: generate_affiliate_link(
                merchant_url=merchant_url,
                campaign=campaign,
                source=source,
                medium=medium,
                content=content,
                term=term,
                extra_params=extra_params,
            ).as_dict(),
            output_taint=Taint.TRUSTED,
        )
    )

    # email.send — APPROVE-tier SMTP send. Closes the outreach loop.
    ts.register(
        Tool(
            name="email.send",
            action="send_email",
            fn=lambda to, subject, body, cc=None, bcc=None: _as_dict(
                plan_email_send(
                    to=to, subject=subject, body=body, cc=cc, bcc=bcc,
                )
            ),
            output_taint=Taint.TRUSTED,
            has_egress=True,
        )
    )

    # email.deliverability_check — AUTO-tier DNS read. No auth, no mutation.
    ts.register(
        Tool(
            name="email.deliverability_check",
            action="read_local_files",
            fn=lambda domain, dkim_selectors=None: check_deliverability(
                domain, dkim_selectors=dkim_selectors,
            ).as_dict(),
            output_taint=Taint.TRUSTED,
            has_egress=True,
        )
    )

    # email.inbox.read — AUTO-tier IMAP fetch. Read-only (readonly=True at
    # SELECT), refuses plaintext port 143, surfaces lead signals only.
    ts.register(
        Tool(
            name="email.inbox.read",
            action="read_local_files",
            fn=lambda folder="INBOX", limit=10, unread_only=True: read_inbox(
                folder=folder,
                limit=int(limit),
                unread_only=bool(unread_only),
            ).as_dict(),
            output_taint=Taint.UNTRUSTED,
            has_egress=True,
        )
    )

    # web.automate — APPROVE-tier interactive automation. Egress at execute time.
    ts.register(
        Tool(
            name="web.automate",
            action="execute_code",
            fn=lambda start_url, actions, timeout_seconds=60.0,
            allow_disallowed_robots=False: _as_dict(
                plan_web_automate(
                    start_url=start_url,
                    actions=actions,
                    timeout_seconds=float(timeout_seconds),
                    allow_disallowed_robots=bool(allow_disallowed_robots),
                )
            ),
            output_taint=Taint.UNTRUSTED,
            has_egress=True,
        )
    )

    # web.scrape — render-aware fetch (Playwright). AUTO-tier read with egress.
    # Output is UNTRUSTED (page content is data, never instructions). Robots.txt
    # is respected by default; the captcha detector triggers a clean stop.
    ts.register(
        Tool(
            name="web.scrape",
            action="read_local_files",  # AUTO-tier; pattern matches research.run
            fn=lambda url, allow_disallowed=False, timeout_seconds=30.0: _scrape_payload(
                web_scrape(
                    url,
                    allow_disallowed=bool(allow_disallowed),
                    timeout_seconds=float(timeout_seconds),
                )
            ),
            output_taint=Taint.UNTRUSTED,
            has_egress=True,
        )
    )

    # http.fetch — read-only egress, output is UNTRUSTED data (trifecta guard applies).
    if fetcher is not None:
        ts.register(
            Tool(
                name="http.fetch",
                action="read_local_files",
                fn=lambda url: _http_payload(http_fetch(url, fetcher=fetcher)),
                output_taint=Taint.UNTRUSTED,
                has_egress=True,
            )
        )
    # docx.draft — APPROVE-tier artifact (behind [docs] extra at runtime).
    def _docx_plan(path: str, title: str, body: str) -> dict[str, Any]:
        from .tools.docx import plan_docx

        return _as_dict(plan_docx(guard, path, title=title, body=body))

    ts.register(
        Tool(
            name="docx.draft",
            action="repo_write",
            fn=_docx_plan,
            output_taint=Taint.TRUSTED,
        )
    )

    # code.complex — delegate heavy coding tasks to a local Claude Code CLI.
    # Approval-gated; the subagent uses its own auth, never MIDAS's keys.
    ts.register(
        Tool(
            name="code.complex",
            action="execute_code",
            fn=lambda prompt, workdir, timeout_seconds=300.0: _as_dict(
                plan_code_complex(
                    prompt=prompt,
                    workdir=workdir,
                    timeout_seconds=float(timeout_seconds),
                )
            ),
            output_taint=Taint.UNTRUSTED,  # subagent output is data, not commands
        )
    )

    ts.register(
        Tool(
            name="code.run",
            action="execute_code",
            # APPROVE-tier — the underlying subprocess never spawns from invoke().
            fn=lambda code, language="python", timeout=10.0: _as_dict(
                plan_code_run(code, language=language, timeout=timeout)
            ),
            output_taint=Taint.UNTRUSTED,
        )
    )

    # ── cash-shaped artifacts (WS2) — all APPROVE-tier, no egress, no scripts.
    ts.register(
        Tool(
            name="landing.draft",
            action="repo_write",
            fn=lambda path, headline, cta_text, subheading="", body="", cta_href="#": _as_dict(
                plan_landing(
                    guard, path,
                    headline=headline, subheading=subheading, body=body,
                    cta_text=cta_text, cta_href=cta_href,
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="product.draft",
            action="repo_write",
            fn=lambda path, title, deliverables, audience="", problem="", price_usd=0.0: _as_dict(
                plan_product(
                    guard, path,
                    title=title, audience=audience, problem=problem,
                    deliverables=deliverables, price_usd=price_usd,
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="outreach.sequence",
            action="repo_write",
            fn=lambda path, audience, offer, steps: _as_dict(
                plan_outreach_sequence(
                    guard, path, audience=audience, offer=offer, steps=steps
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    def _proposal_plan(
        path: str, client: str, project: str, scope: list[str], price_usd: float,
        timeline: str = "", currency: str = "USD",
    ) -> dict[str, Any]:
        return _as_dict(
            plan_proposal(
                guard, path,
                client=client, project=project, scope=scope,
                price_usd=price_usd, timeline=timeline, currency=currency,
            )
        )

    ts.register(
        Tool(
            name="proposal.draft",
            action="repo_write",
            fn=_proposal_plan,
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="quote.draft",
            action="repo_write",
            fn=lambda path, client, items, currency="USD", quote_number="", notes="": _as_dict(
                plan_quote(
                    guard, path,
                    client=client, items=items, currency=currency,
                    quote_number=quote_number, notes=notes,
                )
            ),
            output_taint=Taint.TRUSTED,
        )
    )
    ts.register(
        Tool(
            name="adcopy.draft",
            action="repo_write",
            fn=lambda path, product, audience, variants: _as_dict(
                plan_adcopy(guard, path, product=product, audience=audience, variants=variants)
            ),
            output_taint=Taint.TRUSTED,
        )
    )

    # Skill loader on-demand — the planner sees only the index by default and
    # pulls a specific body when one matches. Both AUTO-tier (read_local_files).
    if skill_registry is not None:
        ts.register(
            Tool(
                name="skill.index",
                action="read_local_files",
                fn=lambda: {
                    "skills": [
                        {
                            "name": e.name,
                            "summary": e.summary,
                            "permissions": e.permissions,
                            "sha256": e.sha256,
                        }
                        for e in skill_index(skill_registry)
                    ]
                },
                output_taint=Taint.TRUSTED,
            )
        )
        ts.register(
            Tool(
                name="skill.load",
                action="read_local_files",
                fn=lambda name: _as_dict(skill_load(skill_registry, name)),
                # SKILL.md bodies come from local disk written by the operator
                # or installed-via-approval; treat as trusted for planning use.
                output_taint=Taint.TRUSTED,
            )
        )

    # stripe.payment_link — closes the cash loop. Approval-gated, no egress at
    # plan time. STRIPE_API_KEY is only read at execute time.
    ts.register(
        Tool(
            name="stripe.payment_link",
            action="publish_public",
            fn=lambda description, amount_usd, currency="USD", product_name="": _as_dict(
                plan_payment_link(
                    description=description,
                    amount_usd=float(amount_usd),
                    currency=currency,
                    product_name=product_name,
                )
            ),
            output_taint=Taint.UNTRUSTED,
            has_egress=True,
        )
    )

    # social.publish — approval-gated, egress at execute time only.
    # Action ``publish_public`` is in the default policy's requires_approval set.
    # Output is UNTRUSTED: the platform's API response is data, not instructions.
    ts.register(
        Tool(
            name="social.publish",
            action="publish_public",
            fn=lambda platform, text, account_handle, media_paths=None: _as_dict(
                plan_social_publish(
                    guard,
                    platform=platform,
                    text=text,
                    account_handle=account_handle,
                    media_paths=media_paths,
                )
            ),
            output_taint=Taint.UNTRUSTED,
            has_egress=True,
        )
    )

    # voice.synthesize — TTS, sibling pattern to image.draft. Offline backend
    # is always available; openai backend egresses with operator's key.
    ts.register(
        Tool(
            name="voice.synthesize",
            action="repo_write",
            fn=lambda path, text, provider="offline", voice="alloy": _as_dict(
                plan_voice_synth(
                    guard, path, text=text, provider=provider, voice=voice
                )
            ),
            output_taint=Taint.TRUSTED,
            has_egress=True,
        )
    )

    # image.draft — provider-agnostic. The offline backend is always available;
    # the openai backend egresses at plan-time when OPENAI_API_KEY is set. Bytes
    # land in the approval payload; the file is written post-approval only.
    ts.register(
        Tool(
            name="image.draft",
            action="repo_write",
            fn=lambda path, prompt, provider="offline", size="512x512": _as_dict(
                plan_image(guard, path, prompt=prompt, provider=provider, size=size)
            ),
            output_taint=Taint.TRUSTED,
            has_egress=True,  # openai backend egresses; offline does not
        )
    )
    return ts


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": value}
