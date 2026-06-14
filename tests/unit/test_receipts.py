"""Receipts ledger: a clean chain verifies; any tamper is detected."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from midas.core.receipts import Decision, ReceiptLedger, Signer, Taint, verify_chain

SEED_A = "11" * 32
SEED_B = "22" * 32


def _signer() -> Signer:
    return Signer.from_hex_seed(SEED_A)


def _fresh_ledger() -> tuple[ReceiptLedger, Signer]:
    signer = _signer()
    path = Path(tempfile.mkdtemp()) / "receipts.jsonl"
    return ReceiptLedger(path, signer), signer


def _append_n(led: ReceiptLedger, n: int) -> None:
    for i in range(n):
        led.append(
            run_id="r1",
            agent="scout",
            tool="web_search",
            decision=Decision.ALLOW,
            inputs={"q": i},
            outputs={"hits": i},
            cost_usd=0.001 * i,
            taint_out=Taint.UNTRUSTED,
        )


def test_clean_chain_verifies() -> None:
    led, signer = _fresh_ledger()
    _append_n(led, 5)
    res = verify_chain(led.path, signer.public_key_hex)
    assert res.ok
    assert res.count == 5


def test_content_tamper_breaks_chain() -> None:
    led, signer = _fresh_ledger()
    _append_n(led, 3)
    lines = led.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["body"]["cost_usd"] = 999.0  # tamper without recomputing hash
    lines[1] = json.dumps(rec)
    led.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not verify_chain(led.path, signer.public_key_hex).ok


def test_forged_hash_fails_signature() -> None:
    led, signer = _fresh_ledger()
    _append_n(led, 3)
    lines = led.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["body"]["cost_usd"] = 999.0
    # Attacker also recomputes a matching hash, but cannot forge the signature.
    from midas.core.receipts.models import ReceiptBody

    rec["hash"] = ReceiptBody.model_validate(rec["body"]).compute_hash()
    lines[1] = json.dumps(rec)
    led.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    res = verify_chain(led.path, signer.public_key_hex)
    assert not res.ok


def test_wrong_public_key_fails() -> None:
    led, _ = _fresh_ledger()
    _append_n(led, 2)
    other = Signer.from_hex_seed(SEED_B)
    assert not verify_chain(led.path, other.public_key_hex).ok


def test_reopen_continues_chain() -> None:
    led, signer = _fresh_ledger()
    _append_n(led, 1)
    led2 = ReceiptLedger(led.path, signer)  # reopen same file
    _append_n(led2, 1)
    res = verify_chain(led.path, signer.public_key_hex)
    assert res.ok
    assert res.count == 2


@settings(max_examples=40, deadline=None)
@given(target=st.integers(min_value=0, max_value=4), field=st.sampled_from(["agent", "tool", "run_id"]))
def test_property_any_field_tamper_detected(target: int, field: str) -> None:
    signer = _signer()
    path = Path(tempfile.mkdtemp()) / "receipts.jsonl"
    led = ReceiptLedger(path, signer)
    _append_n(led, 5)
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[target])
    rec["body"][field] = str(rec["body"][field]) + "_tampered"
    lines[target] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not verify_chain(path, signer.public_key_hex).ok
