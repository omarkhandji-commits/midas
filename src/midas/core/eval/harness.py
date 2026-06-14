"""Eval harness — reproducible, vendor-neutral, deterministic.

Why this exists: a Proof-First claim is only credible if the underlying behavior can
be measured by anyone, the same way, on a different machine. The harness lets us
publish a Transparency Report (not a vanity benchmark we score ourselves) — each row
points to an `Eval` whose code anyone can read and rerun.

Design choices to defend the result against gaming:
- inputs are explicit and stored alongside the eval (no hidden test sets);
- the run is fully offline / deterministic (mocked LLM via injected `complete_fn`);
- per-case outcomes carry the expected vs actual values so a reader can audit them;
- aggregate verdict is binary (`pass`/`fail`) on a stated success-rate threshold,
  with the raw scores reported — no curve-fitting, no cherry-pick.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    name: str
    passed: bool
    expected: Any
    actual: Any
    note: str = ""


@dataclass
class EvalResult:
    eval_name: str
    cases: list[CaseResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    threshold: float = 1.0  # the success-rate at which the eval is considered "passed"

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def verdict(self) -> str:
        return "pass" if self.rate >= self.threshold else "fail"


@dataclass
class Eval:
    """One Eval is a name + a function that produces a list of CaseResult."""

    name: str
    description: str
    run: Callable[[], list[CaseResult]]
    threshold: float = 1.0  # default: every case must pass

    def execute(self) -> EvalResult:
        t0 = time.monotonic()
        cases = list(self.run())
        return EvalResult(
            eval_name=self.name, cases=cases,
            elapsed_seconds=time.monotonic() - t0, threshold=self.threshold,
        )


@dataclass
class Suite:
    name: str
    evals: list[Eval]

    def run(self) -> list[EvalResult]:
        return [e.execute() for e in self.evals]
