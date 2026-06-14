"""WhatsApp adapter (Meta Cloud API).

WhatsApp's Cloud API supports interactive `button` messages whose `id` field carries
arbitrary payload — we use the same `apv:approve:<id>` format. Sending requires a
24-hour conversation window or an approved template (Meta's anti-spam rule); the
adapter just builds the message shape, the operator's run loop handles delivery.

Lazy import note: no Python SDK is required — Meta's API is plain HTTP, so the
production runtime uses `httpx` (already in deps).
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import ApprovalChannel, ChannelConfig, keyboard_buttons


@dataclass
class WhatsAppConfig(ChannelConfig):
    access_token: str = ""
    phone_number_id: str = ""  # Meta WA business number id

    @classmethod
    def make(cls, *, access_token: str, owner_phone: str, phone_number_id: str) -> WhatsAppConfig:
        return cls(
            name="whatsapp", owner_id=str(owner_phone),
            access_token=access_token, phone_number_id=phone_number_id,
        )


class WhatsAppBot(ApprovalChannel):
    def __init__(self, config: WhatsAppConfig, queue, **kw) -> None:
        super().__init__(config, queue, **kw)
        self._config: WhatsAppConfig = config

    def interactive_payload(self, approval_id: int, body_text: str) -> dict:
        """Meta WA Cloud-API 'interactive' message: up to 3 reply buttons."""
        buttons = keyboard_buttons(approval_id)
        return {
            "messaging_product": "whatsapp",
            "to": self._config.owner_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["callback_data"], "title": b["text"]}}
                        for b in buttons
                    ]
                },
            },
        }


__all__ = ["WhatsAppBot", "WhatsAppConfig"]
