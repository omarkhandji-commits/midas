"""Router data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Optional[float] = None  # filled by the cost function if the provider didn't report it
