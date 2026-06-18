"""lead.record — promote inbox messages to cash-signal memory entries.

Why
---
`email.inbox.read` returns recent UNSEEN messages tagged as UNTRUSTED data.
A reply from a prospect is the first observable step of a cash loop: it
deserves to land in the operator's persistent memory so the planner can
later bias outreach toward "channels that paid". Without this bridge, the
inbox fetch is wasted — the signal evaporates at the end of the turn.

Contract
--------
- AUTO-tier (``read_local_files``), no egress.
- Input is a list of message dicts (typically the ``messages`` field of
  ``email.inbox.read``'s output). Strings only — UNTRUSTED data is matched
  against a fixed keyword list, never executed.
- Idempotent: dedup key is ``lead:{from_addr}:{uid}``. Re-running the tool
  with the same inbox payload is a no-op (the MemoryStore supersede
  semantics would otherwise hide older live entries).
- Writes ``MemoryKind.RESULT`` with tags ``["lead", "cash-signal"]``. We
  do NOT write ``MemoryKind.CASH`` because no money has changed hands yet
  — the cash trail is reserved for attributed revenue. The ``cash-signal``
  tag is what biases the planner without lying about the proof level.

Honest constraints
------------------
- We do NOT claim a message is a lead just because the sender's domain is
  unfamiliar. The classifier looks for intent words (``interested``,
  ``demo``, ``quote``, ``price``, ``buy``, ``budget``, ``invoice``, …)
  in subject or snippet. Anything else is ``skipped_not_lead``.
- We do NOT auto-reply, auto-add to a sequence, or auto-mark as read.
  This tool is a memory writer, not a CRM action.
- Proof level is ``LOW``: the inbox snippet is the only evidence and it
  is UNTRUSTED. Sources stay empty so the Proof-First guard accepts it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from midas.core.memory import MemoryKind, MemoryStore


class LeadRecordError(RuntimeError):
    """Raised when leads can't be recorded honestly."""


# Intent words that promote a message from "noise" to "lead". Kept small and
# conservative — false positives waste planner attention; false negatives
# just mean the operator triages manually.
_LEAD_KEYWORDS = (
    "interested",
    "demo",
    "quote",
    "price",
    "pricing",
    "buy",
    "purchase",
    "order",
    "budget",
    "invoice",
    "proposal",
    "rfp",
    "rfq",
    "consult",
    "hire",
    "engage",
    "onboard",
    "subscribe",
    "trial",
    "discount",
    "contract",
)

_MAX_MESSAGES = 100


@dataclass(frozen=True)
class RecordedLead:
    uid: str
    from_addr: str
    key: str
    matched_keyword: str


@dataclass
class LeadRecordResult:
    recorded: list[RecordedLead] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_not_lead: int = 0
    skipped_malformed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "recorded": [
                {
                    "uid": r.uid,
                    "from_addr": r.from_addr,
                    "key": r.key,
                    "matched_keyword": r.matched_keyword,
                }
                for r in self.recorded
            ],
            "recorded_count": len(self.recorded),
            "skipped_existing": self.skipped_existing,
            "skipped_not_lead": self.skipped_not_lead,
            "skipped_malformed": self.skipped_malformed,
        }


def _classify(subject: str, snippet: str) -> str | None:
    """Return the first lead keyword found, or None."""
    hay = f"{subject}\n{snippet}".lower()
    for kw in _LEAD_KEYWORDS:
        if kw in hay:
            return kw
    return None


def _already_recorded(store: MemoryStore, key: str) -> bool:
    """True if a live RESULT entry with this key already exists."""
    rows = store.recall(kind=MemoryKind.RESULT, limit=1)
    for r in rows:
        if r.key == key:
            return True
    # The recall() above filters by kind but not by key directly, so for
    # large memories we still want a focused check. Use the history view.
    try:
        history = store.history(MemoryKind.RESULT, key)
    except Exception:  # noqa: BLE001 - empty key, malformed store, etc.
        history = []
    return any(not h.superseded for h in history)


def record_leads(
    *,
    messages: list[dict[str, Any]],
    store_path: str | Path,
) -> LeadRecordResult:
    """Promote lead-shaped inbox messages into MemoryKind.RESULT entries."""
    if not isinstance(messages, list):
        raise LeadRecordError("messages must be a list of dicts")
    if len(messages) > _MAX_MESSAGES:
        raise LeadRecordError(
            f"refusing to record {len(messages)} messages in one pass "
            f"(cap is {_MAX_MESSAGES}); batch the call"
        )

    store = MemoryStore(store_path)
    result = LeadRecordResult()

    for msg in messages:
        if not isinstance(msg, dict):
            result.skipped_malformed += 1
            continue
        uid = str(msg.get("uid", "")).strip()
        from_addr = str(msg.get("from_addr", "")).strip().lower()
        subject = str(msg.get("subject", "")).strip()
        snippet = str(msg.get("snippet", "")).strip()
        if not uid or not from_addr:
            result.skipped_malformed += 1
            continue

        matched = _classify(subject, snippet)
        if matched is None:
            result.skipped_not_lead += 1
            continue

        key = f"lead:{from_addr}:{uid}"
        if _already_recorded(store, key):
            result.skipped_existing += 1
            continue

        outcome = (
            f"Inbound lead from {from_addr} "
            f'(subject: "{subject[:120]}") — matched intent word "{matched}".'
        )
        store.remember(
            MemoryKind.RESULT,
            key,
            outcome,
            tags=["lead", "cash-signal"],
        )
        result.recorded.append(
            RecordedLead(
                uid=uid,
                from_addr=from_addr,
                key=key,
                matched_keyword=matched,
            )
        )

    return result
