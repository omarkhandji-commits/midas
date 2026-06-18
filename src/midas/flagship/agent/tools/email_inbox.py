"""email.inbox.read — pull recent unread leads from an IMAP mailbox.

Why
---
The cash-shaped tools drive *outbound* (proposal, outreach, social publish).
Inbound is where money actually walks in: reply-from-prospect, demo
request, support-leading-to-upsell, payment notification email. Surfacing
the latest unread messages as structured lead signals lets the agent
prioritize follow-up without manual triage.

Contract
--------
- AUTO-tier (``read_local_files`` action with ``has_egress=True``). The
  read is non-mutating: we do NOT mark messages as read on the server,
  we do NOT move them, we do NOT delete. The IMAP ``UNSEEN`` query is a
  search, not a state change.
- Credentials are env-only: ``IMAP_HOST``, ``IMAP_USER``, ``IMAP_PASSWORD``,
  optional ``IMAP_PORT`` (default 993). Read at *call time* only.
- Output is ``Taint.UNTRUSTED`` — every word in an inbound email is data
  the agent must not interpret as instructions.

Honest constraints
------------------
- We refuse plaintext IMAP (port 143). Always SSL.
- The body snippet is capped at 500 chars per message. Full bodies are a
  read-the-message-later concern, not a triage concern.
- We do NOT parse attachments. Operator opens those manually.
- We do NOT auto-decide a message is a "lead" — that's downstream. We
  return structured rows; the planner classifies.
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import os
from contextlib import suppress
from dataclasses import dataclass, field
from email.message import Message
from typing import Any


class InboxError(RuntimeError):
    """Raised when the IMAP fetch can't run honestly."""


@dataclass(frozen=True)
class InboxMessage:
    uid: str
    from_addr: str
    from_name: str
    subject: str
    snippet: str
    date_iso: str  # ISO-8601 or empty
    has_attachment: bool


@dataclass
class InboxFetch:
    host: str
    folder: str
    fetched_at_iso: str
    messages: list[InboxMessage] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "folder": self.folder,
            "fetched_at_iso": self.fetched_at_iso,
            "messages": [
                {
                    "uid": m.uid,
                    "from_addr": m.from_addr,
                    "from_name": m.from_name,
                    "subject": m.subject,
                    "snippet": m.snippet,
                    "date_iso": m.date_iso,
                    "has_attachment": m.has_attachment,
                }
                for m in self.messages
            ],
        }


_MAX_LIMIT = 50
_SNIPPET_CHARS = 500


def _decode(value: str | None) -> str:
    """Decode RFC 2047 ``=?utf-8?…?=`` headers to plain text."""
    if not value:
        return ""
    try:
        parts = email.header.decode_header(value)
    except Exception:
        return str(value)
    out: list[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out).strip()


def _from_parts(raw: str) -> tuple[str, str]:
    """Split a ``From`` header into (display name, email)."""
    name, addr = email.utils.parseaddr(raw)
    return _decode(name), addr.strip().lower()


def _body_snippet(msg: Message, limit: int = _SNIPPET_CHARS) -> str:
    """Return the first ``limit`` chars of the plain-text body, if any."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")[:limit].strip()
                    except (LookupError, TypeError):
                        return payload.decode("utf-8", errors="replace")[:limit].strip()
        return ""
    payload = msg.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")[:limit].strip()
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")[:limit].strip()


def _has_attachment(msg: Message) -> bool:
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            return True
    return False


def _parse_date_iso(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return ""
    if dt is None:
        return ""
    return dt.isoformat()


def read_inbox(
    *,
    folder: str = "INBOX",
    limit: int = 10,
    unread_only: bool = True,
) -> InboxFetch:
    """Connect IMAP SSL, return up to ``limit`` recent (unread) messages.

    Raises :class:`InboxError` for: missing credentials, port-143 plaintext
    refusal, IMAP login failure, fetch failure.
    """
    host = os.environ.get("IMAP_HOST", "").strip()
    user = os.environ.get("IMAP_USER", "").strip()
    password = os.environ.get("IMAP_PASSWORD", "")
    port_raw = os.environ.get("IMAP_PORT", "993").strip()
    if not host or not user or not password:
        raise InboxError(
            "email.inbox.read needs IMAP_HOST + IMAP_USER + IMAP_PASSWORD"
        )
    try:
        port = int(port_raw)
    except ValueError as e:
        raise InboxError(f"IMAP_PORT must be an integer, got {port_raw!r}") from e
    if port == 143:
        raise InboxError(
            "plaintext IMAP (port 143) refused by policy; use SSL (993)"
        )
    if limit <= 0 or limit > _MAX_LIMIT:
        raise InboxError(f"limit must be in (0, {_MAX_LIMIT}], got {limit}")

    import datetime as _dt

    try:
        conn = imaplib.IMAP4_SSL(host, port)
    except (OSError, imaplib.IMAP4.error) as e:
        raise InboxError(f"IMAP SSL connect to {host}:{port} failed: {e}") from e
    try:
        try:
            conn.login(user, password)
        except imaplib.IMAP4.error as e:
            raise InboxError(f"IMAP login failed for {user!r}: {e}") from e
        # readonly=True is the "we are not changing state" promise.
        typ, _ = conn.select(folder, readonly=True)
        if typ != "OK":
            raise InboxError(f"IMAP select {folder!r} failed: {typ}")
        query = "UNSEEN" if unread_only else "ALL"
        typ, data = conn.search(None, query)
        if typ != "OK" or not data or not data[0]:
            return InboxFetch(
                host=host,
                folder=folder,
                fetched_at_iso=_dt.datetime.now(_dt.UTC).isoformat(),
                messages=[],
            )
        ids = data[0].split()
        # Newest first; cap at limit.
        ids = list(reversed(ids))[:limit]
        messages: list[InboxMessage] = []
        for raw_id in ids:
            typ, fetched = conn.fetch(raw_id, "(RFC822)")
            if typ != "OK" or not fetched:
                continue
            for chunk in fetched:
                if not isinstance(chunk, tuple) or len(chunk) < 2:
                    continue
                raw_bytes = chunk[1]
                if not isinstance(raw_bytes, bytes):
                    continue
                msg = email.message_from_bytes(raw_bytes)
                name, addr = _from_parts(msg.get("From", ""))
                messages.append(
                    InboxMessage(
                        uid=raw_id.decode("ascii", errors="replace"),
                        from_addr=addr,
                        from_name=name,
                        subject=_decode(msg.get("Subject", "")),
                        snippet=_body_snippet(msg),
                        date_iso=_parse_date_iso(msg.get("Date")),
                        has_attachment=_has_attachment(msg),
                    )
                )
                break
        return InboxFetch(
            host=host,
            folder=folder,
            fetched_at_iso=_dt.datetime.now(_dt.UTC).isoformat(),
            messages=messages,
        )
    finally:
        with suppress(Exception):
            conn.logout()
