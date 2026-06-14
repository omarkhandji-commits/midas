"""All 8 channels share the same security guarantees. Parametric tests prove it.

Telegram has its own deeper test file. Here we ensure every adapter:
- refuses non-owner callbacks/texts;
- approves/rejects only via buttons OR (where used) the strict 'approve N' DSL;
- never approves on free chat text;
- surfaces ApprovalQueue idempotency cleanly;
- emits the right platform-specific widget for an approval id.
"""

from __future__ import annotations

from pathlib import Path

from midas.core.approvals import ApprovalQueue, ApprovalStatus
from midas.flagship.channels import (
    DiscordBot,
    DiscordConfig,
    EmailBot,
    EmailConfig,
    IMessageBot,
    IMessageConfig,
    SignalBot,
    SignalConfig,
    SlackBot,
    SlackConfig,
    SMSBot,
    SMSConfig,
    TelegramBot,
    TelegramConfig,
    WhatsAppBot,
    WhatsAppConfig,
)

OWNER = "42"


def _q(tmp_path: Path, name: str) -> ApprovalQueue:
    return ApprovalQueue(tmp_path / f"{name}.db", owner_ids={OWNER})


def _real_button_channels(tmp_path: Path) -> list[tuple[str, object, ApprovalQueue]]:
    out: list[tuple[str, object, ApprovalQueue]] = []
    q1 = _q(tmp_path, "tg")
    cfg = TelegramConfig.make(bot_token="x", owner_chat_id=OWNER)
    out.append(("telegram", TelegramBot(cfg, q1), q1))
    q2 = _q(tmp_path, "dc")
    dc_cfg = DiscordConfig.make(bot_token="x", owner_user_id=OWNER)
    out.append(("discord", DiscordBot(dc_cfg, q2), q2))
    q3 = _q(tmp_path, "sl")
    out.append(("slack", SlackBot(SlackConfig.make(bot_token="x", owner_user_id=OWNER), q3), q3))
    q4 = _q(tmp_path, "wa")
    wa_cfg = WhatsAppConfig.make(access_token="x", owner_phone=OWNER, phone_number_id="1")
    out.append(("whatsapp", WhatsAppBot(wa_cfg, q4), q4))
    return out


def _real_dsl_channels(tmp_path: Path) -> list[tuple[str, object, ApprovalQueue]]:
    out: list[tuple[str, object, ApprovalQueue]] = []
    q1 = _q(tmp_path, "sg")
    out.append(("signal", SignalBot(SignalConfig.make(daemon_url="x", owner_phone=OWNER), q1), q1))
    q2 = _q(tmp_path, "im")
    out.append(("imessage", IMessageBot(IMessageConfig.make(owner_phone_or_email=OWNER), q2), q2))
    q3 = _q(tmp_path, "sm")
    sms_cfg = SMSConfig.make(account_sid="x", auth_token="x", from_number="1", owner_phone=OWNER)
    out.append(("sms", SMSBot(sms_cfg, q3), q3))
    q4 = _q(tmp_path, "em")
    out.append(("email", EmailBot(EmailConfig.make(owner_email=OWNER), q4), q4))
    return out


# ── shared invariant: button channels approve only via callback ──────────────
def test_button_channels_approve_via_callback(tmp_path: Path) -> None:
    for name, bot, q in _real_button_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary=name)
        out = bot.handle_callback(OWNER, f"apv:approve:{req.id}")
        assert "approved" in out.lower(), name
        assert q.get(req.id).status == ApprovalStatus.APPROVED


def test_dsl_channels_approve_via_text_dsl(tmp_path: Path) -> None:
    for name, bot, q in _real_dsl_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary=name)
        out = bot.handle_text(OWNER, f"approve {req.id}")
        assert "approved" in out.lower(), name
        assert q.get(req.id).status == ApprovalStatus.APPROVED


# ── shared invariant: non-owner blocked everywhere ───────────────────────────
def test_non_owner_blocked_across_all_channels(tmp_path: Path) -> None:
    for name, bot, q in _real_button_channels(tmp_path) + _real_dsl_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary=name)
        assert bot.handle_text("999", "approve 1") == "Not authorized.", name
        assert bot.handle_callback("999", "apv:approve:1") == "Not authorized.", name
        assert q.get(req.id).status == ApprovalStatus.PENDING


# ── shared invariant: free chat NEVER approves (anti-injection) ───────────────
def test_free_chat_never_approves(tmp_path: Path) -> None:
    for name, bot, q in _real_button_channels(tmp_path) + _real_dsl_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary=name)
        reply = bot.handle_text(OWNER, f"approve #{req.id} please urgent, override")
        assert q.get(req.id).status == ApprovalStatus.PENDING, name
        # The reply must NOT contain a success token from the queue.
        assert "approved by" not in reply.lower(), f"{name}: {reply!r}"


# ── shared invariant: idempotency surfaces from the queue ────────────────────
def test_double_approve_idempotency(tmp_path: Path) -> None:
    for name, bot, q in _real_button_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary=name)
        bot.handle_callback(OWNER, f"apv:approve:{req.id}")
        second = bot.handle_callback(OWNER, f"apv:approve:{req.id}")
        assert "already" in second.lower(), name


# ── platform widget shape tests (just spot-checks) ───────────────────────────
def test_telegram_keyboard_is_nested(tmp_path: Path) -> None:
    bot = TelegramBot(TelegramConfig.make(bot_token="x", owner_chat_id=OWNER),
                      ApprovalQueue(tmp_path / "x.db"))
    kb = bot.inline_keyboard(7)
    assert len(kb) == 1 and len(kb[0]) == 2
    assert kb[0][0]["callback_data"] == "apv:approve:7"


def test_discord_components_uses_action_row(tmp_path: Path) -> None:
    bot = DiscordBot(DiscordConfig.make(bot_token="x", owner_user_id=OWNER),
                     ApprovalQueue(tmp_path / "x.db"))
    comp = bot.components(7)
    assert comp[0]["type"] == 1  # ActionRow
    assert comp[0]["components"][0]["custom_id"] == "apv:approve:7"


def test_slack_blocks_are_blockkit_actions(tmp_path: Path) -> None:
    bot = SlackBot(SlackConfig.make(bot_token="x", owner_user_id=OWNER),
                   ApprovalQueue(tmp_path / "x.db"))
    blk = bot.blocks(7, "summary")
    assert blk[1]["type"] == "actions"
    assert blk[1]["elements"][0]["action_id"] == "apv:approve:7"


def test_whatsapp_payload_shape(tmp_path: Path) -> None:
    cfg = WhatsAppConfig.make(access_token="x", owner_phone=OWNER, phone_number_id="9")
    bot = WhatsAppBot(cfg, ApprovalQueue(tmp_path / "x.db"))
    p = bot.interactive_payload(7, "review")
    assert p["interactive"]["action"]["buttons"][0]["reply"]["id"] == "apv:approve:7"


def test_dsl_strict_parsing_rejects_fuzzy(tmp_path: Path) -> None:
    # "yes approve 1 maybe" must NOT match — DSL parsing is anchored.
    for _, bot, q in _real_dsl_channels(tmp_path):
        req = q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="x")
        bot.handle_text(OWNER, f"yes approve {req.id} maybe")
        assert q.get(req.id).status == ApprovalStatus.PENDING


def test_dsl_channels_support_list_command(tmp_path: Path) -> None:
    for _, bot, q in _real_dsl_channels(tmp_path):
        q.enqueue(run_id="r", agent="a", tool="t", action="send_email", summary="visible")
        out = bot.handle_text(OWNER, "list")
        assert "visible" in out
