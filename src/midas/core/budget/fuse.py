"""Budget fuse — reserve-before-spend against hard caps.

Every LLM/tool call passes `BudgetFuse.guard(...)`. The estimated cost is *checked
against the caps before the call runs*; a breach raises `BudgetExceeded` and the call
never executes. Actual cost is committed afterwards. A surprise bill is impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .store import SpendStore

_EPS = 1e-9


class BudgetExceeded(Exception):
    def __init__(self, scope: str, projected: float, cap: float) -> None:
        super().__init__(f"budget '{scope}' exceeded: projected ${projected:.4f} > cap ${cap:.4f}")
        self.scope = scope
        self.projected = projected
        self.cap = cap


@dataclass(frozen=True)
class Caps:
    per_task: float
    daily: float
    monthly: float


def _start_of_day_iso() -> str:
    n = datetime.now(UTC)
    return n.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _start_of_month_iso() -> str:
    n = datetime.now(UTC)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


class BudgetFuse:
    def __init__(self, store: SpendStore, caps: Caps) -> None:
        self.store = store
        self.caps = caps

    def check(self, est_usd: float, *, task_id: str | None = None) -> None:
        """Raise BudgetExceeded if committing `est_usd` now would breach any cap."""
        if task_id is not None:
            projected = self.store.total(task_id=task_id) + est_usd
            if projected > self.caps.per_task + _EPS:
                raise BudgetExceeded("per_task", projected, self.caps.per_task)
        projected_day = self.store.total(since_iso=_start_of_day_iso()) + est_usd
        if projected_day > self.caps.daily + _EPS:
            raise BudgetExceeded("daily", projected_day, self.caps.daily)
        projected_month = self.store.total(since_iso=_start_of_month_iso()) + est_usd
        if projected_month > self.caps.monthly + _EPS:
            raise BudgetExceeded("monthly", projected_month, self.caps.monthly)

    def commit(
        self,
        usd: float,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        kind: str | None = None,
        model: str | None = None,
    ) -> None:
        self.store.record(usd, run_id=run_id, task_id=task_id, kind=kind, model=model)

    def guard(
        self,
        est_usd: float,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        kind: str | None = None,
        model: str | None = None,
    ) -> _Guard:
        return _Guard(self, est_usd, task_id, run_id, kind, model)


class _Guard:
    """Context manager: check on enter (may raise), commit actual on clean exit."""

    def __init__(
        self,
        fuse: BudgetFuse,
        est: float,
        task_id: str | None,
        run_id: str | None,
        kind: str | None,
        model: str | None,
    ) -> None:
        self._fuse = fuse
        self._est = est
        self._task_id = task_id
        self._run_id = run_id
        self._kind = kind
        self._model = model
        self._actual: float | None = None

    def __enter__(self) -> _Guard:
        self._fuse.check(self._est, task_id=self._task_id)
        return self

    def set_actual(self, usd: float) -> None:
        self._actual = usd

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        # Commit the spend only on clean exit; never suppress exceptions (returns None).
        if exc_type is None:
            usd = self._actual if self._actual is not None else self._est
            self._fuse.commit(
                usd, run_id=self._run_id, task_id=self._task_id, kind=self._kind, model=self._model
            )
