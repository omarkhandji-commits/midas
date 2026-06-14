"""Secrets broker — the agent references secrets by handle, never sees raw values.

The model context only ever holds `{{secret:NAME}}` placeholders. Real values are
substituted by `resolve()` at the trusted network boundary, inside an allow-listed,
untainted call — never placed back into model context.
"""

from __future__ import annotations

import re

_REF = re.compile(r"\{\{secret:([A-Za-z0-9_\-.]+)\}\}")


class SecretsBroker:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def register(self, handle: str, value: str) -> None:
        self._store[handle] = value

    def has(self, handle: str) -> bool:
        return handle in self._store

    def reference(self, handle: str) -> str:
        """The placeholder the agent is allowed to pass around."""
        return "{{secret:" + handle + "}}"

    def contains_reference(self, text: str) -> bool:
        return bool(_REF.search(text or ""))

    def resolve(self, text: str) -> str:
        """Substitute real secret values. Call ONLY at the trusted network boundary."""

        def _sub(m: "re.Match[str]") -> str:
            handle = m.group(1)
            if handle not in self._store:
                raise KeyError(f"unknown secret handle: {handle}")
            return self._store[handle]

        return _REF.sub(_sub, text)
