"""Channel connection settings and optional listeners.

The dashboard stores channel tokens by handle, never returns raw values, and every
approval still resolves through the shared ApprovalQueue.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from midas.flagship.channels import TelegramBot, TelegramConfig
from midas.flagship.provider_settings import SecretVault

TELEGRAM_BOT_TOKEN = "TELEGRAM_BOT_TOKEN"
TELEGRAM_OWNER_CHAT_ID = "TELEGRAM_OWNER_CHAT_ID"


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
            ChannelStatus(
                name="discord",
                label="Discord",
                connected=False,
                live_listener=False,
                required=["DISCORD_BOT_TOKEN", "DISCORD_OWNER_USER_ID"],
                missing=["DISCORD_BOT_TOKEN", "DISCORD_OWNER_USER_ID"],
                notes="Planned next; same ApprovalQueue contract.",
            ).to_json(),
            ChannelStatus(
                name="slack",
                label="Slack",
                connected=False,
                live_listener=False,
                required=["SLACK_BOT_TOKEN", "SLACK_OWNER_USER_ID"],
                missing=["SLACK_BOT_TOKEN", "SLACK_OWNER_USER_ID"],
                notes="Planned next; same ApprovalQueue contract.",
            ).to_json(),
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

    def telegram_config(self) -> TelegramConfig | None:
        token = self.vault.get(TELEGRAM_BOT_TOKEN)
        owner = self.vault.get(TELEGRAM_OWNER_CHAT_ID)
        if not token or not owner:
            return None
        return TelegramConfig.make(bot_token=token, owner_chat_id=owner)


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
