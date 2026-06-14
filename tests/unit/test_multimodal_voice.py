"""Multimodal and voice/call planning stay local and approval-first."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from midas.flagship.cli import app
from midas.flagship.multimodal import inspect_media
from midas.flagship.voice import draft_voice_message, plan_call

runner = CliRunner()


def test_inspect_text_file_extracts_local_text(tmp_path: Path) -> None:
    p = tmp_path / "brief.txt"
    p.write_text("hello market", encoding="utf-8")
    result = inspect_media(p)
    assert result.kind == "text"
    assert result.text == "hello market"
    assert len(result.sha256) == 64


def test_audio_uses_transcript_sidecar(tmp_path: Path) -> None:
    p = tmp_path / "note.mp3"
    p.write_bytes(b"audio")
    (tmp_path / "note.mp3.txt").write_text("spoken message", encoding="utf-8")
    result = inspect_media(p)
    assert result.kind == "audio"
    assert result.text == "spoken message"


def test_voice_draft_escapes_ssml() -> None:
    draft = draft_voice_message("A < B & C")
    assert draft.approval_required is True
    assert "&lt;" in draft.ssml and "&amp;" in draft.ssml


def test_call_plan_requires_consent_and_opt_out() -> None:
    call = plan_call(contact_label="Acme", purpose="Discovery", offer="SEO audit")
    assert call.approval_required is True
    assert call.consent_required is True
    assert call.opt_out_required is True
    assert "Is now an okay time?" in call.script


def test_media_cli_inspects_without_external_call(tmp_path: Path) -> None:
    p = tmp_path / "brief.txt"
    p.write_text("local", encoding="utf-8")
    result = runner.invoke(app, ["media", "inspect", str(p)])
    assert result.exit_code == 0, result.stdout
    assert '"kind": "text"' in result.stdout
