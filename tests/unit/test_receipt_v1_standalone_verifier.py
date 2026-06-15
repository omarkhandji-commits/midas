"""Sprint A — Receipt v1 standalone verifier conformance + tamper detection.

These tests import the standalone verifier from ``tools/verify``. They MUST NOT
exercise any code path that depends on ``midas.core.receipts`` — that would defeat
the point of an independent verifier.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_DIR = REPO_ROOT / "tools" / "verify"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "receipts_v1_vector.jsonl"
PUBLIC_KEY_HEX = "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29"


@pytest.fixture(scope="module")
def midas_verify():
    sys.path.insert(0, str(VERIFIER_DIR))
    try:
        import midas_verify  # noqa: PLC0415

        return midas_verify
    finally:
        sys.path.remove(str(VERIFIER_DIR))


def test_standalone_verifier_accepts_known_good_vector(midas_verify) -> None:
    result = midas_verify.verify_chain(FIXTURE, PUBLIC_KEY_HEX)
    assert result.ok is True
    assert result.count == 3
    assert result.error is None


def test_standalone_verifier_does_not_import_midas_core(midas_verify) -> None:
    # The whole moat is that the verifier is independent. If midas.* leaks in,
    # the audit story collapses. Guard it in CI.
    verify_module = sys.modules[midas_verify.verify_chain.__module__]
    source = Path(verify_module.__file__).read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    for line in import_lines:
        assert "midas" not in line, f"verifier leaks midas.* import: {line!r}"


def test_byte_tamper_detected_at_first_corrupted_seq(
    midas_verify, tmp_path: Path
) -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    tampered = raw.replace('"allow"', '"deny"', 1)  # flip first decision
    assert tampered != raw
    out = tmp_path / "tampered.jsonl"
    out.write_text(tampered, encoding="utf-8")

    result = midas_verify.verify_chain(out, PUBLIC_KEY_HEX)
    assert result.ok is False
    assert result.bad_seq == 0
    assert "hash mismatch" in (result.error or "")


def test_signature_tamper_detected(midas_verify, tmp_path: Path) -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    # Flip one hex char in the second receipt's signature
    target = '"sig":"b0cb2e72'
    assert raw.count(target) == 1
    tampered = raw.replace(target, '"sig":"00cb2e72', 1)
    out = tmp_path / "bad_sig.jsonl"
    out.write_text(tampered, encoding="utf-8")

    result = midas_verify.verify_chain(out, PUBLIC_KEY_HEX)
    assert result.ok is False
    assert result.bad_seq == 1
    assert "signature" in (result.error or "")


def test_missing_ledger_returns_error(midas_verify, tmp_path: Path) -> None:
    result = midas_verify.verify_chain(tmp_path / "nope.jsonl", PUBLIC_KEY_HEX)
    assert result.ok is False
    assert "not found" in (result.error or "")
