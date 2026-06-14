"""Telegram adapter — operator-facing, over the shared ApprovalChannel."""

from __future__ import annotations

from dataclasses import dataclass

from .base import (
    ApprovalChannel,
    ChannelConfig,
    keyboard_buttons,
    parse_callback,
    render_list,
    render_pending,
)


@dataclass
class TelegramConfig(ChannelConfig):
    bot_token: str = ""

    @classmethod
    def make(cls, *, bot_token: str, owner_chat_id: str) -> TelegramConfig:
        return cls(name="telegram", owner_id=str(owner_chat_id), bot_token=bot_token)


class TelegramBot(ApprovalChannel):
    """Thin Telegram wrapper. Inert until `run()` (production) is wired."""

    def __init__(self, config: TelegramConfig, queue, **kw) -> None:
        super().__init__(config, queue, **kw)
        self._config: TelegramConfig = config

    def inline_keyboard(self, approval_id: int) -> list[list[dict[str, str]]]:
        """Telegram requires nested rows; map the generic buttons accordingly."""
        return [keyboard_buttons(approval_id)]


__all__ = [
    "TelegramBot",
    "TelegramConfig",
    "parse_callback",
    "render_pending",
    "render_list",
]
