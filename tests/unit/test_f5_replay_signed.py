"""Sprint F5 — deterministic replay + signed skill bundles."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision
from midas.flagship.replay import replay_run
from midas.flagship.signed_skills import (
    export_signed_skill,
    import_signed_skill,
    verify_signed_skill,
)
from midas.flagship.skills import SkillRegistry

# ── replay ────────────────────────────────────────────────────────────────────


def test_replay_reproduces_transcript_shape(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f5" * 32))
    for tool in ("fs.read", "research.run", "artifact.text"):
        ledger.append(
            run_id="rep", agent="a", tool=tool,
            decision=Decision.ALLOW if tool != "artifact.text" else Decision.QUEUE_APPROVAL,
            inputs={"t": tool}, outputs={},
        )
    a = replay_run(ledger, "rep")
    b = replay_run(ledger, "rep")
    assert a.signature() == b.signature()
    assert a.tools_used == ["fs.read", "research.run", "artifact.text"]
    assert a.step_count == 3


def test_replay_filters_to_run_id(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f5" * 32))
    ledger.append(run_id="r1", agent="a", tool="x",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    ledger.append(run_id="r2", agent="a", tool="y",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    transcript = replay_run(ledger, "r1")
    assert transcript.tools_used == ["x"]


def test_replay_empty_when_run_id_unknown(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("f5" * 32))
    ledger.append(run_id="exists", agent="a", tool="x",
                  decision=Decision.ALLOW, inputs={}, outputs={})
    transcript = replay_run(ledger, "nope")
    assert transcript.step_count == 0
    assert transcript.tools_used == []


# ── signed skills ────────────────────────────────────────────────────────────


def _make_skill_source(root: Path) -> Path:
    source = root / "src"
    source.mkdir()
    (source / "SKILL.md").write_text("# market-radar-pro\n\nWatch competitors.\n", encoding="utf-8")
    (source / "helper.py").write_text("print('hi')\n", encoding="utf-8")
    return source


def test_export_then_verify_signed_skill(tmp_path: Path) -> None:
    source = _make_skill_source(tmp_path)
    signer = Signer.generate()
    bundle = export_signed_skill(
        source, tmp_path / "bundle", signer,
        name="market-radar-pro", version="0.2.0",
    )
    result = verify_signed_skill(bundle)
    assert result.ok is True
    assert result.manifest is not None
    assert result.manifest.name == "market-radar-pro"
    assert "SKILL.md" in result.manifest.files
    assert result.public_key_hex == signer.public_key_hex


def test_signed_skill_tamper_detected(tmp_path: Path) -> None:
    source = _make_skill_source(tmp_path)
    signer = Signer.generate()
    bundle = export_signed_skill(
        source, tmp_path / "bundle", signer, name="market-radar-pro",
    )
    # Tamper with a payload file AFTER signing.
    (bundle / "helper.py").write_text("print('tampered')\n", encoding="utf-8")
    result = verify_signed_skill(bundle)
    assert result.ok is False
    assert "file hash" in (result.error or "")


def test_signed_skill_bad_signature_detected(tmp_path: Path) -> None:
    source = _make_skill_source(tmp_path)
    signer = Signer.generate()
    bundle = export_signed_skill(
        source, tmp_path / "bundle", signer, name="market-radar-pro",
    )
    sig_path = bundle / "manifest.sig"
    data = sig_path.read_text(encoding="utf-8").replace(signer.public_key_hex[:4], "ffff")
    sig_path.write_text(data, encoding="utf-8")
    result = verify_signed_skill(bundle)
    assert result.ok is False


def test_import_signed_skill_routes_through_install_local(tmp_path: Path) -> None:
    source = _make_skill_source(tmp_path)
    signer = Signer.generate()
    bundle = export_signed_skill(
        source, tmp_path / "bundle", signer, name="market-radar-pro",
    )
    registry = SkillRegistry(tmp_path / "reg")
    info = import_signed_skill(bundle, registry)
    assert info["name"] == "market-radar-pro"
    assert info["signer_public_key_hex"] == signer.public_key_hex
    assert (tmp_path / "reg" / "skills" / "market-radar-pro" / "SKILL.md").exists()


def test_import_signed_skill_refuses_bad_signature(tmp_path: Path) -> None:
    source = _make_skill_source(tmp_path)
    signer = Signer.generate()
    bundle = export_signed_skill(
        source, tmp_path / "bundle", signer, name="market-radar-pro",
    )
    # Wipe the signature.
    (bundle / "manifest.sig").write_text("{}", encoding="utf-8")
    registry = SkillRegistry(tmp_path / "reg")
    with pytest.raises(PermissionError, match="verification failed"):
        import_signed_skill(bundle, registry)
