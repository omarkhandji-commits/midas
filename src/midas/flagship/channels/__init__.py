"""Channels — operator-facing surfaces over a single ApprovalChannel security model.

All channels share the same guarantees: owner-gated, strict callback parse, text never
approves, queue-level idempotency. Each adapter only translates platform events into
`handle_callback(chat_id, data)` / `handle_text(chat_id, text)` and maps the generic
button data to its platform widgets.
"""

from .base import (
    ApprovalChannel,
    ChannelConfig,
    keyboard_buttons,
    parse_callback,
    render_list,
    render_pending,
)
from .discord_bot import DiscordBot, DiscordConfig
from .email_bot import EmailBot, EmailConfig
from .imessage_bot import IMessageBot, IMessageConfig
from .signal_bot import SignalBot, SignalConfig
from .slack_bot import SlackBot, SlackConfig
from .sms_bot import SMSBot, SMSConfig
from .telegram_bot import TelegramBot, TelegramConfig
from .whatsapp_bot import WhatsAppBot, WhatsAppConfig

__all__ = [
    # base
    "ApprovalChannel",
    "ChannelConfig",
    "parse_callback",
    "keyboard_buttons",
    "render_pending",
    "render_list",
    # adapters
    "TelegramBot", "TelegramConfig",
    "DiscordBot", "DiscordConfig",
    "SlackBot", "SlackConfig",
    "WhatsAppBot", "WhatsAppConfig",
    "SignalBot", "SignalConfig",
    "IMessageBot", "IMessageConfig",
    "SMSBot", "SMSConfig",
    "EmailBot", "EmailConfig",
]
