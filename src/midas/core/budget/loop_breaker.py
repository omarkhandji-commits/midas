"""Loop-breaker — four independent trips that kill runaway agent loops.

Trips on: max iterations, wall-clock, token budget, AND a *no-progress* detector that
hashes the canonical loop state and trips when it repeats. Progress, not just spend,
is watched — so an agent that spins without changing state is stopped early.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


class LoopBroken(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"loop-breaker tripped: {reason}")
        self.reason = reason


@dataclass
class LoopBreaker:
    max_iterations: int = 50
    max_wall_seconds: float = 300.0
    max_tokens: int = 1_000_000
    max_no_progress: int = 3

    _iter: int = 0
    _tokens: int = 0
    _start: float = field(default_factory=time.monotonic)
    _last_state: str | None = None
    _no_progress: int = 0

    def tick(self, *, state: Any = None, tokens: int = 0) -> None:
        """Call once per agent step. Raises LoopBroken when a limit is hit."""
        self._iter += 1
        self._tokens += tokens

        if self._iter > self.max_iterations:
            raise LoopBroken("max_iterations")
        if time.monotonic() - self._start > self.max_wall_seconds:
            raise LoopBroken("wall_clock")
        if self._tokens > self.max_tokens:
            raise LoopBroken("token_budget")

        if state is not None:
            h = hashlib.sha256(
                json.dumps(state, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            if h == self._last_state:
                self._no_progress += 1
                if self._no_progress >= self.max_no_progress:
                    raise LoopBroken("no_progress")
            else:
                self._no_progress = 0
                self._last_state = h
