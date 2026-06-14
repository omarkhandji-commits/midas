"""Channel connection settings and optional listeners.

The dashboard stores channel tokens by handle, never returns raw values, and every
approval still resolves through the shared ApprovalQueue.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from midas.flagship.channels import (
    DiscordBot,
    DiscordConfig,
    EmailBot,
    EmailConfig,
    SlackBot,
    SlackConfig,
    SMSBot,
    SMSConfig,
    TelegramBot,
    TelegramConfig,
    WhatsAppBot,
    WhatsAppConfig,
)
from midas.flagship.provider_settings import SecretVault

TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
TELEGRAM_OWNER_CHAT_ID = "TELEGRAM_OWNER_CHAT_ID"
DISCORD_BOT_TOKEN = "DISCORD_BOT_TOKEN"
DISCORD_OWNER_USER_ID = "DISCORD_OWNER_USER_ID"
DISCORD_GUILD_ID = "DISCORD_GUILD_ID"
SLACK_BOT_TOKEN = "SLACK_BOT_TOKEN"
SLACK_OWNER_USER_ID = "SLACK_OWNER_USER_ID"
SLACK_SIGNING_SECRET = "SLACK_SIGNING_SECRET"
WHATSAPP_ACCESS_TOKEN = "WHATSAPP_ACCESS_TOKEN"
WHATSAPP_OWNER_PHONE = "WHATSAPP_OWNER_PHONE"
WHATSAPP_PHONE_NUMBER_ID = "WHATSAPP_PHONE_NUMBER_ID"
EMAIL_OWNER_EMAIL = "EMAIL_OWNER_EMAIL"
EMAIL_SMTP_HOST = "EMAIL_SMTP_HOST"
EMAIL_SMTP_USER = "EMAIL_SMTP_USER"
EMAIL_SMTP_PASS = "EMAIL_SMTP_PASS"
SMS_ACCOUNT_SID = "SMS_ACCOUNT_SID"
SMS_AUTH_TOKEN = "SMS_AUTH_TOKEN"
SMS_FROM_NUMBER = "SMS_FROM_NUMBER"
SMS_OWNER_PHONE = "SMS_OWNER_PHONE"


@dataclass(frozen=True)
class ChannelStatus:
    name: str
    label: str
    connected: bool
    live_listener: bool
    required: list[str]
    missing: list[str]
    notes: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class ChannelManager:
    def __init__(self, vault: SecretVault) -> None:
        self.vault = vault

    def list_statuses(self) -> list[dict[str, Any]]:
        return [
            self.telegram_status().to_json(),
            self.discord_status().to_json(),
            self.slack_status().to_json(),
            self.whatsapp_status().to_json(),
            self.email_status().to_json(),
            self.sms_status().to_json(),
        ]

    def telegram_status(self) -> ChannelStatus:
        missing = [
            handle
            for handle in (TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID)
            if not self.vault.get(handle)
        ]
        return ChannelStatus(
            name="telegram",
            label="Telegram",
            connected=not missing,
            live_listener=True,
            required=[TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID],
            missing=missing,
            notes="Long-poll listener; owner-gated callbacks only.",
        )

    def discord_status(self) -> ChannelStatus:
        missing = [
            handle
            for handle in (DISCORD_BOT_TOKEN, DISCORD_OWNER_USER_ID)
            if not self.vault.get(handle)
        ]
        return ChannelStatus(
            name="discord",
            label="Discord",
            connected=not missing,
            live_listener=True,
            required=[DISCORD_BOT_TOKEN, DISCORD_OWNER_USER_ID],
            missing=missing,
            notes="Button interaction bridge; owner-gated callbacks only.",
        )

    def slack_status(self) -> ChannelStatus:
        missing = [
            handle
            for handle in (SLACK_BOT_TOKEN, SLACK_OWNER_USER_ID)
            if not self.vault.get(handle)
        ]
        return ChannelStatus(
            name="slack",
            label="Slack",
            connected=not missing,
            live_listener=True,
            required=[SLACK_BOT_TOKEN, SLACK_OWNER_USER_ID],
            missing=missing,
            notes="Block Kit action bridge; owner-gated callbacks only.",
        )

    def whatsapp_status(self) -> ChannelStatus:
        required = [WHATSAPP_ACCESS_TOKEN, WHATSAPP_OWNER_PHONE, WHATSAPP_PHONE_NUMBER_ID]
        missing = [handle for handle in required if not self.vault.get(handle)]
        return ChannelStatus(
            name="whatsapp",
            label="WhatsApp",
            connected=not missing,
            live_listener=True,
            required=required,
            missing=missing,
            notes="Cloud API approval buttons; outbound sends stay approval-gated.",
        )

    def email_status(self) -> ChannelStatus:
        missing = [handle for handle in (EMAIL_OWNER_EMAIL,) if not self.vault.get(handle)]
        return ChannelStatus(
            name="email",
            label="Email",
            connected=not missing,
            live_listener=True,
            required=[EMAIL_OWNER_EMAIL],
            missing=missing,
            notes="Draft-only email approval bridge; no auto-send by default.",
        )

    def sms_status(self) -> ChannelStatus:
        required = [SMS_ACCOUNT_SID, SMS_AUTH_TOKEN, SMS_FROM_NUMBER, SMS_OWNER_PHONE]
        missing = [handle for handle in required if not self.vault.get(handle)]
        return ChannelStatus(
            name="sms",
            label="SMS",
            connected=not missing,
            live_listener=True,
            required=required,
            missing=missing,
            notes="Twilio-style approval replies; outbound SMS remains approval-gated.",
        )

    def connect_telegram(self, *, bot_token: str, owner_chat_id: str) -> ChannelStatus:
        if not bot_token.strip():
            raise ValueError("bot_token required")
        if not owner_chat_id.strip():
            raise ValueError("owner_chat_id required")
        self.vault.set(TELEGRAM_BOT_TOKEN, bot_token.strip())
        self.vault.set(TELEGRAM_OWNER_CHAT_ID, owner_chat_id.strip())
        return self.telegram_status()

    def remove_telegram(self) -> ChannelStatus:
        self.vault.delete(TELEGRAM_BOT_TOKEN)
        self.vault.delete(TELEGRAM_OWNER_CHAT_ID)
        return self.telegram_status()

    def connect_discord(
        self, *, bot_token: str, owner_user_id: str, guild_id: str = ""
    ) -> ChannelStatus:
        self._require(bot_token, "bot_token")
        self._require(owner_user_id, "owner_user_id")
        self.vault.set(DISCORD_BOT_TOKEN, bot_token.strip())
        self.vault.set(DISCORD_OWNER_USER_ID, owner_user_id.strip())
        if guild_id.strip():
            self.vault.set(DISCORD_GUILD_ID, guild_id.strip())
        return self.discord_status()

    def remove_discord(self) -> ChannelStatus:
        self.vault.delete(DISCORD_BOT_TOKEN)
        self.vault.delete(DISCORD_OWNER_USER_ID)
        self.vault.delete(DISCORD_GUILD_ID)
        return self.discord_status()

    def connect_slack(
        self, *, bot_token: str, owner_user_id: str, signing_secret: str = ""
    ) -> ChannelStatus:
        self._require(bot_token, "bot_token")
        self._require(owner_user_id, "owner_user_id")
        self.vault.set(SLACK_BOT_TOKEN, bot_token.strip())
        self.vault.set(SLACK_OWNER_USER_ID, owner_user_id.strip())
        if signing_secret.strip():
            self.vault.set(SLACK_SIGNING_SECRET, signing_secret.strip())
        return self.slack_status()

    def remove_slack(self) -> ChannelStatus:
        self.vault.delete(SLACK_BOT_TOKEN)
        self.vault.delete(SLACK_OWNER_USER_ID)
        self.vault.delete(SLACK_SIGNING_SECRET)
        return self.slack_status()

    def connect_whatsapp(
        self, *, access_token: str, owner_phone: str, phone_number_id: str
    ) -> ChannelStatus:
        self._require(access_token, "access_token")
        self._require(owner_phone, "owner_phone")
        self._require(phone_number_id, "phone_number_id")
        self.vault.set(WHATSAPP_ACCESS_TOKEN, access_token.strip())
        self.vault.set(WHATSAPP_OWNER_PHONE, owner_phone.strip())
        self.vault.set(WHATSAPP_PHONE_NUMBER_ID, phone_number_id.strip())
        return self.whatsapp_status()

    def remove_whatsapp(self) -> ChannelStatus:
        self.vault.delete(WHATSAPP_ACCESS_TOKEN)
        self.vault.delete(WHATSAPP_OWNER_PHONE)
        self.vault.delete(WHATSAPP_PHONE_NUMBER_ID)
        return self.whatsapp_status()

    def connect_email(
        self,
        *,
        owner_email: str,
        smtp_host: str = "",
        smtp_user: str = "",
        smtp_pass: str = "",
    ) -> ChannelStatus:
        self._require(owner_email, "owner_email")
        self.vault.set(EMAIL_OWNER_EMAIL, owner_email.strip())
        if smtp_host.strip():
            self.vault.set(EMAIL_SMTP_HOST, smtp_host.strip())
        if smtp_user.strip():
            self.vault.set(EMAIL_SMTP_USER, smtp_user.strip())
        if smtp_pass.strip():
            self.vault.set(EMAIL_SMTP_PASS, smtp_pass.strip())
        return self.email_status()

    def remove_email(self) -> ChannelStatus:
        self.vault.delete(EMAIL_OWNER_EMAIL)
        self.vault.delete(EMAIL_SMTP_HOST)
        self.vault.delete(EMAIL_SMTP_USER)
        self.vault.delete(EMAIL_SMTP_PASS)
        return self.email_status()

    def connect_sms(
        self, *, account_sid: str, auth_token: str, from_number: str, owner_phone: str
    ) -> ChannelStatus:
        self._require(account_sid, "account_sid")
        self._require(auth_token, "auth_token")
        self._require(from_number, "from_number")
        self._require(owner_phone, "owner_phone")
        self.vault.set(SMS_ACCOUNT_SID, account_sid.strip())
        self.vault.set(SMS_AUTH_TOKEN, auth_token.strip())
        self.vault.set(SMS_FROM_NUMBER, from_number.strip())
        self.vault.set(SMS_OWNER_PHONE, owner_phone.strip())
        return self.sms_status()

    def remove_sms(self) -> ChannelStatus:
        self.vault.delete(SMS_ACCOUNT_SID)
        self.vault.delete(SMS_AUTH_TOKEN)
        self.vault.delete(SMS_FROM_NUMBER)
        self.vault.delete(SMS_OWNER_PHONE)
        return self.sms_status()

    def test_telegram(self) -> dict[str, Any]:
        status = self.telegram_status()
        message = (
            "Telegram credentials are present."
            if status.connected
            else "Missing fields."
        )
        return {
            "ok": status.connected,
            "channel": "telegram",
            "message": message,
            "missing": status.missing,
        }

    def test_discord(self) -> dict[str, Any]:
        return _test_result("discord", self.discord_status())

    def test_slack(self) -> dict[str, Any]:
        return _test_result("slack", self.slack_status())

    def test_whatsapp(self) -> dict[str, Any]:
        return _test_result("whatsapp", self.whatsapp_status())

    def test_email(self) -> dict[str, Any]:
        result = _test_result("email", self.email_status())
        if result["ok"]:
            result["message"] = "Email draft-only approval bridge is configured."
        return result

    def test_sms(self) -> dict[str, Any]:
        return _test_result("sms", self.sms_status())

    def telegram_config(self) -> TelegramConfig | None:
        token = self.vault.get(TELEGRAM_BOT_TOKEN)
        owner = self.vault.get(TELEGRAM_OWNER_CHAT_ID)
        if not token or not owner:
            return None
        return TelegramConfig.make(bot_token=token, owner_chat_id=owner)

    def discord_config(self) -> DiscordConfig | None:
        token = self.vault.get(DISCORD_BOT_TOKEN)
        owner = self.vault.get(DISCORD_OWNER_USER_ID)
        if not token or not owner:
            return None
        return DiscordConfig.make(
            bot_token=token,
            owner_user_id=owner,
            guild_id=self.vault.get(DISCORD_GUILD_ID) or "",
        )

    def slack_config(self) -> SlackConfig | None:
        token = self.vault.get(SLACK_BOT_TOKEN)
        owner = self.vault.get(SLACK_OWNER_USER_ID)
        if not token or not owner:
            return None
        return SlackConfig.make(
            bot_token=token,
            owner_user_id=owner,
            signing_secret=self.vault.get(SLACK_SIGNING_SECRET) or "",
        )

    def whatsapp_config(self) -> WhatsAppConfig | None:
        token = self.vault.get(WHATSAPP_ACCESS_TOKEN)
        owner = self.vault.get(WHATSAPP_OWNER_PHONE)
        phone_number_id = self.vault.get(WHATSAPP_PHONE_NUMBER_ID)
        if not token or not owner or not phone_number_id:
            return None
        return WhatsAppConfig.make(
            access_token=token,
            owner_phone=owner,
            phone_number_id=phone_number_id,
        )

    def email_config(self) -> EmailConfig | None:
        owner = self.vault.get(EMAIL_OWNER_EMAIL)
        if not owner:
            return None
        return EmailConfig.make(
            owner_email=owner,
            smtp_host=self.vault.get(EMAIL_SMTP_HOST) or "",
            smtp_user=self.vault.get(EMAIL_SMTP_USER) or "",
            smtp_pass=self.vault.get(EMAIL_SMTP_PASS) or "",
        )

    def sms_config(self) -> SMSConfig | None:
        account_sid = self.vault.get(SMS_ACCOUNT_SID)
        auth_token = self.vault.get(SMS_AUTH_TOKEN)
        from_number = self.vault.get(SMS_FROM_NUMBER)
        owner = self.vault.get(SMS_OWNER_PHONE)
        if not account_sid or not auth_token or not from_number or not owner:
            return None
        return SMSConfig.make(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            owner_phone=owner,
        )

    @staticmethod
    def _require(value: str, field: str) -> None:
        if not value.strip():
            raise ValueError(f"{field} required")


class TelegramLongPollListener:
    """Minimal Telegram long-poll bridge into ApprovalChannel."""

    def __init__(
        self,
        *,
        config: TelegramConfig,
        queue: Any,
        poll_seconds: float = 1.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot = TelegramBot(config, queue)
        self.config = config
        self.poll_seconds = poll_seconds
        self._client = client
        self._offset = 0

    async def run_forever(self) -> None:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            while True:
                await self.poll_once(client)
                await asyncio.sleep(self.poll_seconds)
        finally:
            if owns_client:
                await client.aclose()

    async def poll_once(self, client: httpx.AsyncClient) -> None:
        base = f"https://api.telegram.org/bot{self.config.bot_token}"
        response = await client.get(
            f"{base}/getUpdates",
            params={
                "offset": self._offset,
                "timeout": 20,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        response.raise_for_status()
        for update in response.json().get("result", []):
            self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
            reply = self._handle_update(update)
            chat_id = _chat_id(update)
            if reply and chat_id:
                await client.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": reply})
            callback_id = update.get("callback_query", {}).get("id")
            if callback_id:
                await client.post(
                    f"{base}/answerCallbackQuery",
                    json={"callback_query_id": callback_id},
                )

    def _handle_update(self, update: dict[str, Any]) -> str:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            chat_id = str(callback.get("from", {}).get("id", ""))
            data = str(callback.get("data", ""))
            return self.bot.handle_callback(chat_id, data)
        message = update.get("message")
        if isinstance(message, dict):
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = str(message.get("text", ""))
            return self.bot.handle_text(chat_id, text)
        return ""


def _chat_id(update: dict[str, Any]) -> str:
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        message = callback.get("message")
        if isinstance(message, dict):
            return str(message.get("chat", {}).get("id", ""))
        return str(callback.get("from", {}).get("id", ""))
    message = update.get("message")
    if isinstance(message, dict):
        return str(message.get("chat", {}).get("id", ""))
    return ""


class DiscordInteractionHandler:
    def __init__(self, *, config: DiscordConfig, queue: Any) -> None:
        self.bot = DiscordBot(config, queue)

    def handle_interaction(self, payload: dict[str, Any]) -> str:
        user_id = str(payload.get("member", {}).get("user", {}).get("id", ""))
        data = str(payload.get("data", {}).get("custom_id", ""))
        return self.bot.handle_callback(user_id, data)


class SlackActionHandler:
    def __init__(self, *, config: SlackConfig, queue: Any) -> None:
        self.bot = SlackBot(config, queue)

    def handle_action(self, payload: dict[str, Any]) -> str:
        user_id = str(payload.get("user", {}).get("id", ""))
        actions = payload.get("actions")
        if not isinstance(actions, list) or not actions:
            return "Unrecognized action."
        action_id = str(actions[0].get("action_id", ""))
        return self.bot.handle_callback(user_id, action_id)


class WhatsAppWebhookHandler:
    def __init__(self, *, config: WhatsAppConfig, queue: Any) -> None:
        self.bot = WhatsAppBot(config, queue)

    def handle_webhook(self, payload: dict[str, Any]) -> str:
        message = _first_whatsapp_message(payload)
        if not message:
            return ""
        sender = str(message.get("from", ""))
        interactive = message.get("interactive")
        if isinstance(interactive, dict):
            button = interactive.get("button_reply")
            if isinstance(button, dict):
                return self.bot.handle_callback(sender, str(button.get("id", "")))
        text = message.get("text")
        if isinstance(text, dict):
            return self.bot.handle_text(sender, str(text.get("body", "")))
        return "Unrecognized action."


class EmailReplyHandler:
    def __init__(self, *, config: EmailConfig, queue: Any) -> None:
        self.bot = EmailBot(config, queue)

    def handle_reply(self, *, from_email: str, body: str) -> str:
        return self.bot.handle_text(from_email, body)


class SMSReplyHandler:
    def __init__(self, *, config: SMSConfig, queue: Any) -> None:
        self.bot = SMSBot(config, queue)

    def handle_message(self, *, from_phone: str, body: str) -> str:
        return self.bot.handle_text(from_phone, body)


def _test_result(channel: str, status: ChannelStatus) -> dict[str, Any]:
    message = (
        f"{status.label} credentials are present."
        if status.connected
        else "Missing fields."
    )
    return {
        "ok": status.connected,
        "channel": channel,
        "message": message,
        "missing": status.missing,
    }


def _first_whatsapp_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        if not isinstance(changes, list):
            continue
        for change in changes:
            value = change.get("value") if isinstance(change, dict) else None
            messages = value.get("messages") if isinstance(value, dict) else None
            if isinstance(messages, list) and messages and isinstance(messages[0], dict):
                return messages[0]
    return None
