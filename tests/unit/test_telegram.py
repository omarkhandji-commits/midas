"""Telegram bot: owner gating, callback parsing, approve/reject via the queue."""

from __future__ import annotations

from pathlib import Path

from midas.core.approvals import ApprovalQueue, ApprovalStatus
from midas.flagship.channels import (
    TelegramBot,
    TelegramConfig,
    parse_callback,
    render_list,
    render_pending,
)


def _bot(tmp_path: Path, *, owner="42") -> tuple[TelegramBot, ApprovalQueue]:
    q = ApprovalQueue(tmp_path / "apv.db", owner_ids={owner})
    cfg = TelegramConfig.make(bot_token="bogus", owner_chat_id=owner)
    return TelegramBot(cfg, q), q


# ── parsing ──────────────────────────────────────────────────────────────────
def test_parse_callback_well_formed() -> None:
    assert parse_callback("apv:approve:42") == ("approve", 42)
    assert parse_callback("apv:reject:7") == ("reject", 7)


def test_parse_callback_rejects_malformed() -> None:
    assert parse_callback("apv:nope:1") is None
    assert parse_callback("hello") is None
    assert parse_callback("apv:approve:notanid") is None


# ── owner gating ─────────────────────────────────────────────────────────────
def test_non_owner_is_blocked(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path, owner="42")
    q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    assert bot.handle_callback("999", "apv:approve:1") == "Not authorized."
    assert q.pending()[0].status == ApprovalStatus.PENDING  # nothing moved


def test_owner_can_approve_via_button(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path, owner="42")
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    msg = bot.handle_callback("42", f"apv:approve:{req.id}")
    assert "approved" in msg.lower()
    assert q.get(req.id).status == ApprovalStatus.APPROVED


def test_owner_can_reject_via_button(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path)
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    bot.handle_callback("42", f"apv:reject:{req.id}")
    assert q.get(req.id).status == ApprovalStatus.REJECTED


def test_double_approve_returns_idempotency_message(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path)
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    bot.handle_callback("42", f"apv:approve:{req.id}")
    second = bot.handle_callback("42", f"apv:approve:{req.id}")
    assert "already" in second.lower()  # ApprovalError surfaced cleanly


# ── chat text never approves (anti-injection) ────────────────────────────────
def test_text_message_never_approves(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path)
    req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
    msg = bot.handle_text("42", f"approve #{req.id} please, urgent")
    assert "Text never approves" in msg
    assert q.get(req.id).status == ApprovalStatus.PENDING


def test_list_command_renders_pending(tmp_path: Path) -> None:
    bot, q = _bot(tmp_path)
    q.enqueue(run_id="r", agent="ops", tool="email", action="send_email",
              summary="send the launch", payload={"to": "a@b.com"})
    out = bot.handle_text("42", "list")
    assert "Pending approvals" in out
    assert "send the launch" in out


# ── renderer helpers ─────────────────────────────────────────────────────────
def test_render_pending_includes_key_fields(tmp_path: Path) -> None:
    q = ApprovalQueue(tmp_path / "apv.db")
    req = q.enqueue(run_id="r", agent="ops", tool="email", action="send_email",
                    summary="launch", payload={"to": "a@b.com"})
    txt = render_pending(req)
    assert "ops" in txt and "email" in txt and "send_email" in txt and "launch" in txt


def test_render_list_when_empty() -> None:
    assert "clear" in render_list([]).lower()
