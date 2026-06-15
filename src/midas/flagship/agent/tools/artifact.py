"""Artifact factory — the débrouillard surface.

The agent must NEVER refuse a request for output. If a specialized tool fits
(``sheet.write``, ``pdf.draft``, ``email.draft``, ``voice.draft``,
``invoice.draft``, ``code.draft``), the planner uses it. Otherwise it falls
back to ``artifact.text`` which writes a Markdown best-effort with a clearly
labeled "what I would need to do this better" footer.

All artifact tools are APPROVE-tier (mapped to ``repo_write``): the bytes live
inside the approval payload, only an explicit human resolution turns them into
files. Receipts record path + sha256 of the proposed bytes, never the prose.

Cross-cuts:
- :func:`plan_artifact_*` builds the approval payload; no disk write.
- :func:`execute_artifact_*` is the post-approval writer (called via
  :mod:`midas.flagship.agent.execute`).
- Everything goes through :class:`FsGuard` — workspace-only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from midas.flagship.assets.documents import simple_pdf_bytes
from midas.flagship.voice import draft_voice_message

from .fs import execute_fs_write
from .fsguard import FsGuard

ArtifactKind = Literal[
    "text", "markdown", "email", "pdf", "invoice", "voice", "code", "html"
]


@dataclass
class ArtifactPlan:
    """Approval payload for any artifact write."""

    kind: ArtifactKind
    path: str
    bytes_len: int
    sha256_new: str
    sha256_prev: str | None = None
    preview: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_prev(target: Path) -> str | None:
    if not target.exists() or not target.is_file():
        return None
    return _sha256(target.read_bytes())


def _preview_text(data: bytes, limit: int = 400) -> str:
    try:
        return data[:limit].decode("utf-8")
    except UnicodeDecodeError:
        return "(binary)"


# ── text / markdown ──────────────────────────────────────────────────────────


def plan_artifact_text(
    guard: FsGuard, path: str, content: str, *, kind: ArtifactKind = "text"
) -> ArtifactPlan:
    target = guard.resolve(path)
    data = content.encode("utf-8")
    return ArtifactPlan(
        kind=kind,
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=content[:400],
    )


# ── email draft (.eml + .md companion) ───────────────────────────────────────


def plan_artifact_email(
    guard: FsGuard,
    path: str,
    *,
    to: str,
    subject: str,
    body: str,
    from_: str = "",
    cc: str = "",
) -> ArtifactPlan:
    if not to.strip():
        raise ValueError("email needs a non-empty `to`")
    eml = _build_eml(to=to, subject=subject, body=body, from_=from_, cc=cc)
    target = guard.resolve(path)
    data = eml.encode("utf-8")
    return ArtifactPlan(
        kind="email",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=eml[:400],
        meta={"to": to, "subject": subject, "cc": cc, "from": from_},
    )


def _build_eml(*, to: str, subject: str, body: str, from_: str, cc: str) -> str:
    lines = [f"To: {to}", f"Subject: {subject}"]
    if from_:
        lines.insert(0, f"From: {from_}")
    if cc:
        lines.append(f"Cc: {cc}")
    lines.append("Content-Type: text/plain; charset=utf-8")
    lines.append("")
    lines.append(body)
    return "\r\n".join(lines) + "\r\n"


# ── pdf (real bytes via existing simple_pdf_bytes) ───────────────────────────


def plan_artifact_pdf(
    guard: FsGuard, path: str, *, title: str, body: str
) -> ArtifactPlan:
    target = guard.resolve(path)
    if target.suffix.lower() != ".pdf":
        raise ValueError(f"pdf path must end in .pdf, got {target.suffix!r}")
    data = simple_pdf_bytes(title, body)
    return ArtifactPlan(
        kind="pdf",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=f"{title}\n\n{body[:400]}",
        meta={"title": title},
    )


# ── invoice (PDF with structured line items + total) ─────────────────────────


def _build_invoice_body(
    *,
    to: str,
    items: list[Any],  # each entry is (label, qty, unit_price)-shaped
    currency: str,
    invoice_number: str,
    notes: str,
) -> str:
    if not items:
        raise ValueError("invoice needs at least one line item")
    lines: list[str] = [f"INVOICE {invoice_number}".strip(), "", f"To: {to}", ""]
    total = 0.0
    for entry in items:
        label, qty, unit = entry[0], float(entry[1]), float(entry[2])
        amount = qty * unit
        total += amount
        lines.append(f"{label}  -  {qty} x {unit:.2f} = {amount:.2f} {currency}")
    lines.append("")
    lines.append(f"TOTAL: {total:.2f} {currency}")
    if notes.strip():
        lines.append("")
        lines.append(f"Notes: {notes.strip()}")
    return "\n".join(lines)


def plan_artifact_invoice(
    guard: FsGuard,
    path: str,
    *,
    to: str,
    items: list[tuple[str, float, float]],
    currency: str = "USD",
    invoice_number: str = "",
    notes: str = "",
) -> ArtifactPlan:
    body = _build_invoice_body(
        to=to, items=items, currency=currency,
        invoice_number=invoice_number, notes=notes,
    )
    return plan_artifact_pdf(
        guard,
        path,
        title=f"Invoice {invoice_number}".strip() or "Invoice",
        body=body,
    )


# ── voice (text + SSML; .mp3 only if a TTS adapter is wired) ─────────────────


def plan_artifact_voice(
    guard: FsGuard,
    path: str,
    *,
    text: str,
    channel: str = "voice_note",
) -> ArtifactPlan:
    draft = draft_voice_message(text, channel=channel)
    target = guard.resolve(path)
    # We persist a deterministic, no-network artifact: the SSML script + plain text.
    # If a TTS adapter is registered in a future iteration, the executor can emit
    # an audio file alongside this; the approval card already carries the script.
    payload = f"# Voice draft ({draft.channel})\n\n{draft.text}\n\n---\n\n{draft.ssml}\n"
    data = payload.encode("utf-8")
    return ArtifactPlan(
        kind="voice",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=payload[:400],
        meta={"channel": draft.channel, "ssml_len": len(draft.ssml)},
    )


# ── code (any language → a file with the right extension) ────────────────────


def plan_artifact_code(
    guard: FsGuard,
    path: str,
    *,
    content: str,
    language: str = "python",
) -> ArtifactPlan:
    target = guard.resolve(path)
    data = content.encode("utf-8")
    return ArtifactPlan(
        kind="code",
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_prev(target),
        preview=content[:400],
        meta={"language": language},
    )


# ── execute (post-approval) ──────────────────────────────────────────────────


def execute_artifact(guard: FsGuard, payload: dict[str, Any]) -> ArtifactPlan:
    """Materialize an APPROVED artifact plan. Used by the execute step."""
    kind = str(payload.get("kind") or "text")
    path = str(payload.get("path") or "")
    content = payload.get("content")
    if content is None:
        # Some kinds recompute their bytes from their semantic payload so the
        # final write is deterministic — and so the approval card can re-render
        # the exact bytes a reviewer saw.
        if kind == "email":
            content = _build_eml(
                to=str(payload.get("to") or ""),
                subject=str(payload.get("subject") or ""),
                body=str(payload.get("body") or ""),
                from_=str(payload.get("from") or ""),
                cc=str(payload.get("cc") or ""),
            )
        elif kind == "pdf":
            content = simple_pdf_bytes(
                str(payload.get("title") or "Document"),
                str(payload.get("body") or ""),
            )
        elif kind == "voice":
            draft = draft_voice_message(
                str(payload.get("text") or ""),
                channel=str(payload.get("channel") or "voice_note"),
            )
            content = f"# Voice draft ({draft.channel})\n\n{draft.text}\n\n---\n\n{draft.ssml}\n"
        else:
            content = ""
    fs_plan = execute_fs_write(guard, path, content)
    return ArtifactPlan(
        kind=kind,  # type: ignore[arg-type]
        path=fs_plan.path,
        bytes_len=fs_plan.bytes_len,
        sha256_new=fs_plan.sha256_new,
        sha256_prev=fs_plan.sha256_prev,
        preview=fs_plan.preview,
    )
