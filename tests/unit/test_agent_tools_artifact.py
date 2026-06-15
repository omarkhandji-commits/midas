"""Artifact factory — débrouillard surface, never blocks, always gated."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.agent.tools.artifact import (
    execute_artifact,
    plan_artifact_code,
    plan_artifact_email,
    plan_artifact_invoice,
    plan_artifact_pdf,
    plan_artifact_text,
    plan_artifact_voice,
)
from midas.flagship.agent.tools.fsguard import FsGuard


def _g(tmp_path: Path) -> FsGuard:
    return FsGuard(workspace=tmp_path.resolve())


def test_plan_text_does_not_write(tmp_path: Path) -> None:
    plan = plan_artifact_text(_g(tmp_path), "note.md", "# hi", kind="markdown")
    assert plan.kind == "markdown"
    assert plan.bytes_len == 4
    assert plan.sha256_new
    assert not (tmp_path / "note.md").exists()


def test_plan_email_builds_eml_headers(tmp_path: Path) -> None:
    plan = plan_artifact_email(
        _g(tmp_path), "draft.eml",
        to="client@example.com",
        subject="Devis",
        body="Bonjour,\nVoici votre devis.",
        from_="me@example.com",
        cc="boss@example.com",
    )
    assert plan.kind == "email"
    assert "To: client@example.com" in plan.preview
    assert "Subject: Devis" in plan.preview
    assert "From: me@example.com" in plan.preview
    assert "Cc: boss@example.com" in plan.preview
    assert plan.meta["to"] == "client@example.com"


def test_plan_email_rejects_empty_to(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty `to`"):
        plan_artifact_email(_g(tmp_path), "x.eml", to="", subject="s", body="b")


def test_plan_pdf_produces_real_pdf_bytes(tmp_path: Path) -> None:
    plan = plan_artifact_pdf(
        _g(tmp_path), "out.pdf", title="Hello", body="World",
    )
    assert plan.kind == "pdf"
    assert plan.bytes_len > 100
    # Real PDFs start with %PDF-
    raw = execute_artifact(
        _g(tmp_path),
        {"kind": "pdf", "path": str(tmp_path / "out.pdf"), "title": "Hello", "body": "World"},
    )
    assert (tmp_path / "out.pdf").read_bytes().startswith(b"%PDF-")
    assert raw.bytes_len == plan.bytes_len


def test_plan_pdf_rejects_wrong_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must end in .pdf"):
        plan_artifact_pdf(_g(tmp_path), "out.txt", title="x", body="y")


def test_plan_invoice_includes_total_and_items(tmp_path: Path) -> None:
    plan = plan_artifact_invoice(
        _g(tmp_path), "inv.pdf",
        to="Acme Co.",
        items=[("Consulting", 10, 100.0), ("Setup", 1, 250.0)],
        currency="CAD",
        invoice_number="2026-001",
    )
    assert plan.kind == "pdf"
    body = plan.preview
    assert "Acme Co." in body
    assert "Consulting" in body
    assert "1250.00 CAD" in body  # total
    assert "Invoice 2026-001" in body or "2026-001" in body


def test_plan_invoice_rejects_empty_items(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="line item"):
        plan_artifact_invoice(
            _g(tmp_path), "inv.pdf", to="x", items=[],
        )


def test_plan_voice_emits_ssml_and_text(tmp_path: Path) -> None:
    plan = plan_artifact_voice(_g(tmp_path), "msg.md", text="Bonjour, ici MIDAS.")
    assert plan.kind == "voice"
    assert "Bonjour" in plan.preview
    assert "<speak>" in plan.preview
    assert plan.meta["channel"] == "voice_note"


def test_plan_code_carries_language_meta(tmp_path: Path) -> None:
    plan = plan_artifact_code(
        _g(tmp_path), "snippet.py", content="print('x')", language="python"
    )
    assert plan.kind == "code"
    assert plan.meta["language"] == "python"
    assert plan.preview == "print('x')"


def test_execute_email_writes_eml(tmp_path: Path) -> None:
    out = execute_artifact(
        _g(tmp_path),
        {
            "kind": "email", "path": str(tmp_path / "draft.eml"),
            "to": "x@y.com", "subject": "S", "body": "B",
        },
    )
    raw = (tmp_path / "draft.eml").read_text(encoding="utf-8")
    assert "To: x@y.com" in raw
    assert "Subject: S" in raw
    assert out.kind == "email"


def test_execute_voice_writes_script(tmp_path: Path) -> None:
    out = execute_artifact(
        _g(tmp_path),
        {
            "kind": "voice", "path": str(tmp_path / "v.md"),
            "text": "Hello operator.", "channel": "voice_note",
        },
    )
    body = (tmp_path / "v.md").read_text(encoding="utf-8")
    assert "Hello operator." in body
    assert "<speak>" in body
    assert out.kind == "voice"
