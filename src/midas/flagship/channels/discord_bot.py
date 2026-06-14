"""Discord adapter — same approval semantics, Discord widget shape.

Discord uses button components with `custom_id`; we put our generic `apv:approve:<id>`
straight in there. py-cord / discord.py SDKs are lazy imports — install discord extras
only if you actually run this channel.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, keyboard_buttons


@dataclass
class DiscordConfig(ChannelConfig):
    bot_token: str = ""
    guild_id: str = ""  # the server to operate in

    @classmethod
    def make(cls, *, bot_token: str, owner_user_id: str, guild_id: str = "") -> DiscordConfig:
        return cls(
            name="discord", owner_id=str(owner_user_id),
            bot_token=bot_token, guild_id=guild_id,
        )


class DiscordBot(ApprovalChannel):
    def __init__(self, config: DiscordConfig, queue, **kw) -> None:
        super().__init__(config, queue, **kw)
        self._config: DiscordConfig = config

    def components(self, approval_id: int) -> list[dict]:
        """Discord action-row shape: ActionRow → Button list with custom_id."""
        buttons = keyboard_buttons(approval_id)
        return [
            {
                "type": 1,  # ActionRow
                "components": [
                    # style 3 = green (approve), 4 = red (reject)
                    {"type": 2, "style": 3 if b["text"] == "Approve" else 4,
                     "label": b["text"], "custom_id": b["callback_data"]}
                    for b in buttons
                ],
            }
        ]


__all__ = ["DiscordBot", "DiscordConfig"]
