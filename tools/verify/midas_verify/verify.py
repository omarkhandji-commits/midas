"""Receipt v1 verifier — pure reference implementation.

Intentionally minimal: any reader can audit this file end-to-end.
Re-implements the four chain rules from docs/RECEIPT_V1.md without importing
anything from midas.* — only `pynacl` and stdlib.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nacl import encoding, signing
from nacl.exceptions import BadSignatureError

GENESIS_HASH = "0" * 64


@dataclass
class VerifyResult:
    ok: bool
    count: int
    error: str | None = None
    bad_seq: int | None = None


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace. Must match Receipt v1 spec."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_sig(public_key_hex: str, message: str, sig_hex: str) -> bool:
    try:
        vk = signing.VerifyKey(public_key_hex.encode("ascii"), encoder=encoding.HexEncoder)
        vk.verify(message.encode("utf-8"), bytes.fromhex(sig_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


def verify_chain(path: str | Path, public_key_hex: str) -> VerifyResult:
    """Replay a Receipt v1 JSONL ledger and confirm every chain rule holds."""
    p = Path(path)
    if not p.exists():
        return VerifyResult(ok=False, count=0, error=f"ledger not found: {p}", bad_seq=None)

    prev = GENESIS_HASH
    count = 0
    with p.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f):
            line = raw.strip()
            if not line:
                continue
            try:
                receipt = json.loads(line)
                body = receipt["body"]
                stored_hash = receipt["hash"]
                sig_hex = receipt["sig"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                return VerifyResult(False, count, f"parse error at line {lineno}: {exc}", count)

            if body.get("seq") != count:
                return VerifyResult(False, count, f"seq mismatch at index {count}", count)
            if body.get("prev_hash") != prev:
                return VerifyResult(False, count, f"prev_hash break at seq {count}", count)

            recomputed = sha256_hex(canonical_json(body).encode("utf-8"))
            if recomputed != stored_hash:
                return VerifyResult(False, count, f"hash mismatch at seq {count}", count)
            if not _verify_sig(public_key_hex, stored_hash, sig_hex):
                return VerifyResult(False, count, f"bad signature at seq {count}", count)

            prev = stored_hash
            count += 1

    return VerifyResult(ok=True, count=count)
