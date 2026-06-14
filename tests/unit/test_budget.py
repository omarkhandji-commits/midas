"""Budget fuse + loop-breaker: a runaway bill is structurally impossible."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.core.budget import BudgetExceeded, BudgetFuse, Caps, LoopBreaker, LoopBroken, SpendStore


def _caps() -> Caps:
    return Caps(per_task=0.25, daily=2.0, monthly=30.0)


def _fuse(tmp_path: Path) -> tuple[BudgetFuse, SpendStore]:
    store = SpendStore(tmp_path / "spend.db")
    return BudgetFuse(store, _caps()), store


def test_reservation_rejects_per_task_overspend(tmp_path: Path) -> None:
    fuse, _ = _fuse(tmp_path)
    fuse.commit(0.20, task_id="t1")
    with pytest.raises(BudgetExceeded) as exc:
        fuse.check(0.10, task_id="t1")  # 0.30 > 0.25
    assert exc.value.scope == "per_task"


def test_reservation_rejects_daily_overspend(tmp_path: Path) -> None:
    fuse, _ = _fuse(tmp_path)
    fuse.commit(1.95)
    with pytest.raises(BudgetExceeded) as exc:
        fuse.check(0.10)  # 2.05 > 2.0
    assert exc.value.scope == "daily"


def test_guard_blocks_body_before_running(tmp_path: Path) -> None:
    fuse, _ = _fuse(tmp_path)
    fuse.commit(2.0)  # daily cap already reached
    ran = False
    with pytest.raises(BudgetExceeded):
        with fuse.guard(0.01) as _g:
            ran = True  # must never execute — check happens in __enter__
    assert ran is False


def test_guard_commits_actual_cost(tmp_path: Path) -> None:
    fuse, store = _fuse(tmp_path)
    with fuse.guard(0.10, task_id="t1") as g:
        g.set_actual(0.05)
    assert abs(store.total(task_id="t1") - 0.05) < 1e-9


def test_guard_commits_estimate_when_actual_unset(tmp_path: Path) -> None:
    fuse, store = _fuse(tmp_path)
    with fuse.guard(0.07, task_id="t2"):
        pass
    assert abs(store.total(task_id="t2") - 0.07) < 1e-9


def test_spend_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "spend.db"
    BudgetFuse(SpendStore(db), _caps()).commit(0.5)
    assert abs(SpendStore(db).total() - 0.5) < 1e-9


def test_loop_breaker_max_iterations() -> None:
    lb = LoopBreaker(max_iterations=3)
    with pytest.raises(LoopBroken) as exc:
        for _ in range(10):
            lb.tick()
    assert exc.value.reason == "max_iterations"


def test_loop_breaker_token_budget() -> None:
    lb = LoopBreaker(max_iterations=1000, max_tokens=100)
    with pytest.raises(LoopBroken) as exc:
        for _ in range(10):
            lb.tick(tokens=50)
    assert exc.value.reason == "token_budget"


def test_loop_breaker_no_progress_trips() -> None:
    lb = LoopBreaker(max_iterations=1000, max_no_progress=3)
    with pytest.raises(LoopBroken) as exc:
        for _ in range(10):
            lb.tick(state={"plan": "same", "step": "same"})
    assert exc.value.reason == "no_progress"


def test_loop_breaker_real_progress_does_not_trip() -> None:
    lb = LoopBreaker(max_iterations=1000, max_no_progress=3)
    for i in range(20):
        lb.tick(state={"step": i})  # changing state each tick → never trips
