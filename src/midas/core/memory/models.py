"""Memory models — six typed namespaces, each entry Proof-First.

The six kinds match how MIDAS actually reasons about a business:

  USER     — the operator: style, projects, limits, budget.
  BUSINESS — what is sold: offers, audience, prices.
  DECISION — why A was chosen over B (chose / rejected / why).
  RESULT   — what happened: replies, sales, clicks, outcomes (closes Track).
  MARKET   — competitors: prices, offers, content, SEO, ads, changes.
  ERROR    — "last time this didn't work because…" (drives self-improvement).

Every entry carries sources + a proof level + a timestamp. Entries are never edited
in place: an update writes a new row that *supersedes* the old one, so the history
("the last time we tried X") is preserved — that history is the moat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from midas.core.agents.summary import ProofLevel
from midas.core.receipts.models import utcnow_iso


class MemoryKind(StrEnum):
    USER = "user"
    BUSINESS = "business"
    DECISION = "decision"
    RESULT = "result"
    MARKET = "market"
    ERROR = "error"


@dataclass
class MemoryEntry:
    """One remembered fact. `key` groups successive versions of the same fact."""

    kind: MemoryKind
    key: str
    content: str
    proof_level: ProofLevel = ProofLevel.LOW
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    ts: str = field(default_factory=utcnow_iso)
    superseded: bool = False
    id: int | None = None

    def __post_init__(self) -> None:
        # Proof-First: a MEDIUM/HIGH memory must cite at least one source.
        if self.proof_level.rank >= ProofLevel.MEDIUM.rank and not self.sources:
            raise ValueError(
                f"memory '{self.key}' claims proof_level={self.proof_level.value} "
                "but cites no sources"
            )
