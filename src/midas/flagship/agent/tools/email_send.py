"""email.send — APPROVE-tier SMTP send. Closes the outreach loop.

Why
---
``email.draft`` writes an ``.eml`` to disk; ``email.send`` actually puts
it on the wire. Like every other mutating outbound tool, the send is
queued for approval, and the executor only acts after the operator
clicks ✅. The agent cannot, by construction, send mail without the
operator seeing the exact recipients + body + sha256 first.

Contract
--------
- Plan validates recipients, subject, body, optional CC/BCC. NO socket
  opens at plan time. Credentials read only at execute time.
- Payload carries the canonical message + a sha256_intent of
  ``to|cc|bcc|subject|body``; executor refuses on drift.
- Action: ``send_email`` (the policy already lists this — paired with
  ``send_message`` for chat channels). APPROVE-tier by default.
- A failed send writes a DENY receipt — outbox failures are never
  silently swallowed.

Security envelope
-----------------
- STARTTLS is REQUIRED. We refuse plain SMTP (port 25) outright.
- ``SMTP_HOST`` + ``SMTP_USER`` + ``SMTP_PASSWORD`` + ``SMTP_FROM`` read
  from environment at *execute time* only. They never reach the planner.
- We do NOT carry an unsubscribe link if the operator didn't include one.
  We DO refuse to send to >1 recipient with no ``List-Unsubscribe`` /
  unsubscribe text in the body — bulk mail without that header is the
  shape of spam, and modern receivers will treat it as such.
"""

from __future__ import annotations

import email
import email.utils
import hashlib
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any


class SmtpSendError(RuntimeError):
    """Raised when the SMTP send can't be performed honestly."""


_MAX_RECIPIENTS = 100  # sanity cap; operator wanting more wires a real ESP
_MAX_BODY_CHARS = 50_000


@dataclass
class EmailSendPlan:
    kind: str  # always "email_send"
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    sha256_intent: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


def _normalize_recipients(raw: list[str] | str) -> list[str]:
    if isinstance(raw, str):
        candidates = [r for r in raw.split(",")]
    else:
        candidates = list(raw or [])
    cleaned: list[str] = []
    for r in candidates:
        addr = str(r).strip()
        if not addr:
            continue
        # parseaddr returns ("", "") for nonsense; we keep the original lower-case email.
        _, parsed = email.utils.parseaddr(addr)
        if not parsed or "@" not in parsed:
            raise ValueError(f"recipient {addr!r} is not a valid email address")
        cleaned.append(parsed.lower())
    return cleaned


def _hash_intent(
    *, to: list[str], cc: list[str], bcc: list[str], subject: str, body: str
) -> str:
    canonical = (
        "|".join(sorted(to))
        + "||"
        + "|".join(sorted(cc))
        + "||"
        + "|".join(sorted(bcc))
        + "||"
        + subject
        + "||"
        + body
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _looks_unsubscribable(body: str) -> bool:
    """Cheap textual check for an unsubscribe affordance."""
    needle = body.lower()
    return (
        "unsubscribe" in needle
        or "opt-out" in needle
        or "opt out" in needle
        or "list-unsubscribe" in needle
    )


def plan_email_send(
    *,
    to: list[str] | str,
    subject: str,
    body: str,
    cc: list[str] | str | None = None,
    bcc: list[str] | str | None = None,
) -> EmailSendPlan:
    """Build the approval payload. NO SMTP socket opens."""
    if not subject.strip():
        raise ValueError("email.send needs a non-empty subject")
    if not body.strip():
        raise ValueError("email.send needs a non-empty body")
    if len(body) > _MAX_BODY_CHARS:
        raise ValueError(
            f"email.send body too large ({len(body)} > {_MAX_BODY_CHARS})"
        )
    to_list = _normalize_recipients(to)
    cc_list = _normalize_recipients(cc or [])
    bcc_list = _normalize_recipients(bcc or [])
    total = len(to_list) + len(cc_list) + len(bcc_list)
    if total == 0:
        raise ValueError("email.send needs at least one recipient")
    if total > _MAX_RECIPIENTS:
        raise ValueError(
            f"email.send too many recipients ({total} > {_MAX_RECIPIENTS}); "
            "use a real ESP for bulk sends"
        )
    # Bulk mail without an unsubscribe affordance is spam-shaped — receivers
    # will treat it that way. Refuse to plan it.
    if total > 1 and not _looks_unsubscribable(body):
        raise ValueError(
            "email.send to >1 recipient requires an unsubscribe affordance "
            "in the body (the word 'unsubscribe' or a List-Unsubscribe hint); "
            "CAN-SPAM / CASL / GDPR all require it"
        )
    intent = _hash_intent(
        to=to_list, cc=cc_list, bcc=bcc_list, subject=subject, body=body
    )
    preview = f"To: {', '.join(to_list[:3])}{' …' if len(to_list) > 3 else ''}\n"
    preview += f"Subject: {subject}\n\n{body[:300]}"
    return EmailSendPlan(
        kind="email_send",
        to=to_list,
        cc=cc_list,
        bcc=bcc_list,
        subject=subject.strip(),
        body=body,
        sha256_intent=intent,
        preview=preview[:600],
        meta={"n_recipients": total},
    )


@dataclass(frozen=True)
class EmailSendResult:
    message_id: str
    recipients_accepted: int
    raw_status: str


def execute_email_send(payload: dict[str, Any]) -> EmailSendResult:
    """Post-approval send. Reads SMTP_* at this step only."""
    to_list = list(payload.get("to") or [])
    cc_list = list(payload.get("cc") or [])
    bcc_list = list(payload.get("bcc") or [])
    subject = str(payload.get("subject") or "")
    body = str(payload.get("body") or "")
    if not to_list and not cc_list and not bcc_list:
        raise SmtpSendError("email.send payload has no recipients")
    expected = str(payload.get("sha256_intent") or "")
    if expected and _hash_intent(
        to=to_list, cc=cc_list, bcc=bcc_list, subject=subject, body=body
    ) != expected:
        raise SmtpSendError(
            "email.send refused: payload intent hash drifted from approval"
        )

    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", user).strip()
    port_raw = os.environ.get("SMTP_PORT", "587").strip()
    if not host or not user or not password or not from_addr:
        raise SmtpSendError(
            "email.send needs SMTP_HOST + SMTP_USER + SMTP_PASSWORD "
            "(SMTP_FROM defaults to SMTP_USER)"
        )
    try:
        port = int(port_raw)
    except ValueError as e:
        raise SmtpSendError(f"SMTP_PORT must be an integer, got {port_raw!r}") from e
    if port == 25:
        raise SmtpSendError(
            "plaintext SMTP (port 25) refused by policy; use STARTTLS (587) or SSL (465)"
        )

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    message_id = email.utils.make_msgid(domain=host)
    msg["Message-ID"] = message_id
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
                smtp.login(user, password)
                refused = smtp.send_message(msg, to_addrs=to_list + cc_list + bcc_list)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(user, password)
                refused = smtp.send_message(msg, to_addrs=to_list + cc_list + bcc_list)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise SmtpSendError(f"SMTP send failed: {type(e).__name__}: {e}") from e

    accepted = len(to_list) + len(cc_list) + len(bcc_list) - len(refused or {})
    return EmailSendResult(
        message_id=str(message_id),
        recipients_accepted=accepted,
        raw_status="smtp_ok" if not refused else f"smtp_partial({len(refused)}_refused)",
    )
