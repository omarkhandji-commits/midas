"""Slack adapter — Block Kit actions over the shared ApprovalChannel.

Slack signs callbacks server-side; the in-app `action_id` carries our generic
`apv:approve:<id>` payload. Slack Bolt is a lazy import — production deployments wire
the HTTP listener separately.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, keyboard_buttons


@dataclass
class SlackConfig(ChannelConfig):
    bot_token: str = ""
    signing_secret: str = ""

    @classmethod
    def make(cls, *, bot_token: str, owner_user_id: str, signing_secret: str = "") -> SlackConfig:
        return cls(
            name="slack", owner_id=str(owner_user_id),
            bot_token=bot_token, signing_secret=signing_secret,
        )


class SlackBot(ApprovalChannel):
    def __init__(self, config: SlackConfig, queue, **kw) -> None:
        super().__init__(config, queue, **kw)
        self._config: SlackConfig = config

    def blocks(self, approval_id: int, summary: str) -> list[dict]:
        """Slack Block Kit: a section with two action buttons."""
        buttons = keyboard_buttons(approval_id)
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": b["text"]},
                        "action_id": b["callback_data"],
                        "style": "primary" if b["text"] == "Approve" else "danger",
                    }
                    for b in buttons
                ],
            },
        ]


__all__ = ["SlackBot", "SlackConfig"]
