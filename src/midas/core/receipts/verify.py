"""Verify the integrity of a receipt chain (tamper-evidence)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import GENESIS_HASH, Receipt
from .signer import Signer


@dataclass
class VerifyResult:
    ok: bool
    count: int
    error: str | None = None
    bad_seq: int | None = None


def verify_chain(path: str | Path, public_key_hex: str) -> VerifyResult:
    """Recompute every hash, check chain linkage + sequence + Ed25519 signatures.

    Any single mutated byte (content, relinked prev_hash, or forged signature) is
    detected and returns ok=False.
    """
    p = Path(path)
    if not p.exists():
        return VerifyResult(ok=True, count=0)

    prev = GENESIS_HASH
    count = 0
    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = Receipt.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001 - any parse failure = tamper/corruption
                return VerifyResult(False, count, f"parse error at line {lineno}: {exc}", count)
            if r.body.seq != count:
                return VerifyResult(False, count, f"seq mismatch at index {count}", count)
            if r.body.prev_hash != prev:
                return VerifyResult(False, count, f"prev_hash break at seq {count}", count)
            if r.body.compute_hash() != r.hash:
                return VerifyResult(False, count, f"hash mismatch at seq {count}", count)
            if not Signer.verify(public_key_hex, r.hash, r.sig):
                return VerifyResult(False, count, f"bad signature at seq {count}", count)
            prev = r.hash
            count += 1
    return VerifyResult(ok=True, count=count)
