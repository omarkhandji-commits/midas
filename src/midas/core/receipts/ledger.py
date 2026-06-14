"""Append-only, hash-chained, signed receipt ledger (JSONL-backed)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .models import (
    GENESIS_HASH,
    Decision,
    Receipt,
    ReceiptBody,
    Taint,
    digest_payload,
    utcnow_iso,
)
from .signer import Signer


class ReceiptLedger:
    def __init__(self, path: str | Path, signer: Signer) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._signer = signer
        self._lock = threading.Lock()
        self._last_hash, self._seq = self._load_tail()

    def _load_tail(self) -> tuple[str, int]:
        if not self.path.exists():
            return GENESIS_HASH, 0
        last_hash, seq = GENESIS_HASH, 0
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = Receipt.model_validate_json(line)
                last_hash, seq = r.hash, r.body.seq + 1
        return last_hash, seq

    @property
    def public_key_hex(self) -> str:
        return self._signer.public_key_hex

    def append(
        self,
        *,
        run_id: str,
        agent: str,
        tool: str,
        decision: Decision,
        inputs: Any,
        outputs: Any,
        cost_usd: float = 0.0,
        taint_in: Taint = Taint.TRUSTED,
        taint_out: Taint = Taint.TRUSTED,
        approval_id: str | None = None,
    ) -> Receipt:
        with self._lock:
            body = ReceiptBody(
                seq=self._seq,
                prev_hash=self._last_hash,
                ts=utcnow_iso(),
                run_id=run_id,
                agent=agent,
                tool=tool,
                decision=decision,
                inputs_hash=digest_payload(inputs),
                outputs_hash=digest_payload(outputs),
                cost_usd=cost_usd,
                taint_in=taint_in,
                taint_out=taint_out,
                approval_id=approval_id,
            )
            h = body.compute_hash()
            receipt = Receipt(body=body, hash=h, sig=self._signer.sign(h))
            with self.path.open("a", encoding="utf-8") as f:
                f.write(receipt.model_dump_json() + "\n")
            self._last_hash, self._seq = h, self._seq + 1
            return receipt

    def __iter__(self) -> Iterator[Receipt]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield Receipt.model_validate_json(line)
