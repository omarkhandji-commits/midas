"""Data models for the receipts ledger.

A *receipt* is the tamper-evident proof that a tool/LLM action happened. The agent
cannot claim an action without one. Each receipt is hash-chained to the previous and
signed (Ed25519). Inputs/outputs are stored as SHA-256 digests, never the raw payload.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

GENESIS_HASH = "0" * 64


class Taint(str, Enum):
    """Trust label that flows with every payload (drives the Sentinel trifecta rule)."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"  # fetched web/email/doc content — data, never instructions
    PRIVATE = "private"  # secrets, operator data, repo contents


class Decision(str, Enum):
    ALLOW = "allow"
    QUEUE_APPROVAL = "queue_approval"
    DENY = "deny"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, no whitespace) for hashing/signing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def digest_payload(payload: Any) -> str:
    """SHA-256 of an arbitrary payload's canonical JSON (we never store the raw payload)."""
    return sha256_hex(canonical_json(payload).encode("utf-8"))


class ReceiptBody(BaseModel):
    """The hashed + signed content of a receipt."""

    seq: int
    prev_hash: str
    ts: str
    run_id: str
    agent: str
    tool: str
    decision: Decision
    inputs_hash: str
    outputs_hash: str
    cost_usd: float = 0.0
    taint_in: Taint = Taint.TRUSTED
    taint_out: Taint = Taint.TRUSTED
    approval_id: Optional[str] = None

    def canonical(self) -> str:
        return canonical_json(self.model_dump(mode="json"))

    def compute_hash(self) -> str:
        # The body already contains prev_hash + seq, so hashing the canonical body
        # binds this receipt to its position in the chain.
        return sha256_hex(self.canonical().encode("utf-8"))


class Receipt(BaseModel):
    body: ReceiptBody
    hash: str
    sig: str  # hex Ed25519 signature over `hash`

    @property
    def seq(self) -> int:
        return self.body.seq

    @property
    def prev_hash(self) -> str:
        return self.body.prev_hash
