"""Kill switch — one flag that freezes every action."""

from __future__ import annotations


class KillSwitch:
    def __init__(self, engaged: bool = False) -> None:
        self._engaged = engaged

    @property
    def engaged(self) -> bool:
        return self._engaged

    def engage(self) -> None:
        self._engaged = True

    def release(self) -> None:
        self._engaged = False
