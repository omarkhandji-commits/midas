"""newsletter.draft — CAN-SPAM / CASL / GDPR-aware bulk-email artifact.

Why
---
Phase 7 cash vein WS-U. ``email.send`` already refuses bulk (>1
recipient) without an unsubscribe affordance. This tool builds the
artifact that satisfies that check: a body that *guarantees* the
unsubscribe link + physical address are present, in both HTML and
plaintext, with the operator's required language.

Contract
--------
- Plan-only (no egress). Returns the rendered HTML, plaintext, and
  subject for the operator to review. The downstream send goes through
  ``email.send`` (APPROVE-tier).
- We REFUSE to render without an unsubscribe URL and a physical
  postal address — these are legal must-haves in every major
  jurisdiction (CAN-SPAM, CASL, GDPR transparency), not "nice to have".
- HTML output is plain, mobile-friendly, no tracking pixels, no
  third-party fonts. Honesty over polish.

Honest constraints
------------------
- We do NOT inject a tracking pixel or click-tracking redirect.
  Operator can plug those in if they want — the agent stays neutral.
- We do NOT manage subscriber lists here. List + consent management
  is a separate primitive (future slice).
- We do NOT translate. The unsubscribe phrase ships in English; pass
  ``unsubscribe_label`` for any other language.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from typing import Any


class NewsletterError(RuntimeError):
    """Raised when a newsletter can't be rendered honestly."""


_URL_RE = re.compile(r"^https?://[^\s]+$")
_MAX_BODY_CHARS = 100_000
_MAX_SUBJECT_CHARS = 200


@dataclass
class NewsletterDraft:
    kind: str = "newsletter_draft"
    subject: str = ""
    html: str = ""
    plaintext: str = ""
    sha256_intent: str = ""
    unsubscribe_url: str = ""
    physical_address: str = ""
    preview_text: str = ""  # inbox preview (90 chars max — used by clients)
    char_count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _md_lite_to_html(body: str) -> str:
    """Tiny markdown → HTML converter (headings, bold, links, paragraphs).

    No third-party deps. Anything we don't recognize is treated as a
    paragraph with surrounding text escaped.
    """
    out: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = " ".join(paragraph).strip()
        if text:
            out.append(f"<p>{_inline(text)}</p>")
        paragraph.clear()

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("# "):
            flush_paragraph()
            out.append(f"<h1>{_inline(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            flush_paragraph()
            out.append(f"<h2>{_inline(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            flush_paragraph()
            out.append(f"<h3>{_inline(line[4:].strip())}</h3>")
        else:
            paragraph.append(line)
    flush_paragraph()
    return "\n".join(out)


def _inline(text: str) -> str:
    """Inline-level escapes: HTML escape first, then re-allow **bold** + links."""
    esc = html.escape(text, quote=True)
    # Markdown links [label](url) — only allow http(s) destinations.
    def _link(m: re.Match[str]) -> str:
        label = m.group(1)
        url = m.group(2).strip()
        if not _URL_RE.match(url):
            return label  # drop the unsafe href; emit only the label
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'

    esc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, esc)
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
    return esc


_HTML_TEMPLATE = (
    "<!doctype html>\n"
    "<html><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>{subject}</title></head>\n"
    "<body style=\"font-family:sans-serif;max-width:600px;margin:0 auto;"
    "padding:20px;color:#222;\">\n"
    "<div style=\"font-size:0;line-height:0;opacity:0;\">{preview}</div>\n"
    "{body_html}\n"
    "<hr style=\"border:none;border-top:1px solid #ccc;margin:24px 0;\">\n"
    "<p style=\"font-size:12px;color:#666;\">{address}</p>\n"
    "<p style=\"font-size:12px;color:#666;\">"
    '<a href="{unsubscribe}" style="color:#666;">{unsub_label}</a>'
    "</p>\n"
    "</body></html>\n"
)

_PLAINTEXT_FOOTER = "\n\n---\n{address}\n\n{unsub_label}: {unsubscribe}\n"


def plan_newsletter(
    *,
    subject: str,
    body: str,
    unsubscribe_url: str,
    physical_address: str,
    preview_text: str = "",
    unsubscribe_label: str = "Unsubscribe",
) -> NewsletterDraft:
    """Render a CAN-SPAM/CASL-aware newsletter (HTML + plaintext + footer)."""
    subj = subject.strip()
    if not subj:
        raise NewsletterError("newsletter needs a non-empty subject")
    if len(subj) > _MAX_SUBJECT_CHARS:
        raise NewsletterError(
            f"subject is {len(subj)} chars; cap is {_MAX_SUBJECT_CHARS}"
        )
    if not body.strip():
        raise NewsletterError("newsletter needs a non-empty body")
    if len(body) > _MAX_BODY_CHARS:
        raise NewsletterError(
            f"body is {len(body)} chars; cap is {_MAX_BODY_CHARS}"
        )
    if not _URL_RE.match(unsubscribe_url.strip()):
        raise NewsletterError(
            "newsletter REFUSES to render without a valid https unsubscribe URL "
            "(CAN-SPAM/CASL/GDPR — non-negotiable)"
        )
    if len(physical_address.strip()) < 8:
        raise NewsletterError(
            "newsletter REFUSES to render without a physical postal address "
            "(CAN-SPAM 15 U.S.C. §7704(a)(5) — non-negotiable)"
        )

    body_html = _md_lite_to_html(body)
    preview = (preview_text or body).strip().replace("\n", " ")
    preview = preview[:90]

    rendered_html = _HTML_TEMPLATE.format(
        subject=html.escape(subj),
        preview=html.escape(preview),
        body_html=body_html,
        address=html.escape(physical_address.strip()),
        unsubscribe=html.escape(unsubscribe_url.strip(), quote=True),
        unsub_label=html.escape(unsubscribe_label),
    )
    plaintext = body.strip() + _PLAINTEXT_FOOTER.format(
        address=physical_address.strip(),
        unsub_label=unsubscribe_label,
        unsubscribe=unsubscribe_url.strip(),
    )

    canonical = "\n".join([
        subj, body, unsubscribe_url, physical_address, preview, unsubscribe_label,
    ])
    return NewsletterDraft(
        subject=subj,
        html=rendered_html,
        plaintext=plaintext,
        sha256_intent=_sha256(canonical),
        unsubscribe_url=unsubscribe_url.strip(),
        physical_address=physical_address.strip(),
        preview_text=preview,
        char_count=len(body),
    )
