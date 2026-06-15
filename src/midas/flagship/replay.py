"""Deterministic replay — reconstruct the transcript shape of a past run.

Reads every receipt for a given ``run_id`` from the ledger and rebuilds an
:class:`AgentTranscript`-shaped object. Mutations are NOT silently re-applied —
the replay walks the receipts and reports what each step *did*. Used for audit,
debug, and "what did MIDAS do on Tuesday?" answers.

The replay produces an identical transcript shape across calls (same tools, same
decisions, same approval ids, same hashes). If the world changed underneath — a
referenced file is gone, a queued approval was later denied — the replay surfaces
the drift; it does not paper over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReplayStep:
    seq: int
    tool: str
    decision: str
    inputs_hash: str
    outputs_hash: str
    approval_id: str | None
    hash: str
    ts: str


@dataclass
class ReplayTranscript:
    run_id: str
    steps: list[ReplayStep] = field(default_factory=list)
    public_key_hex: str | None = None

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def tools_used(self) -> list[str]:
        return [s.tool for s in self.steps]

    @property
    def queued_approvals(self) -> list[str]:
        return [s.approval_id for s in self.steps if s.approval_id]

    def signature(self) -> tuple[str, ...]:
        """A stable identifier for the transcript shape. Two replays of the same
        ledger MUST produce equal signatures.
        """
        return tuple(f"{s.seq}:{s.tool}:{s.decision}:{s.hash}" for s in self.steps)


def replay_run(ledger: Any, run_id: str) -> ReplayTranscript:
    """Walk the receipt chain and produce a deterministic replay."""
    transcript = ReplayTranscript(run_id=run_id)
    if hasattr(ledger, "public_key_hex"):
        transcript.public_key_hex = ledger.public_key_hex
    for receipt in ledger:
        if receipt.body.run_id != run_id:
            continue
        transcript.steps.append(
            ReplayStep(
                seq=receipt.body.seq,
                tool=receipt.body.tool,
                decision=receipt.body.decision.value,
                inputs_hash=receipt.body.inputs_hash,
                outputs_hash=receipt.body.outputs_hash,
                approval_id=receipt.body.approval_id,
                hash=receipt.hash,
                ts=receipt.body.ts,
            )
        )
    transcript.steps.sort(key=lambda s: s.seq)
    return transcript


def format_replay(transcript: ReplayTranscript) -> str:
    if not transcript.steps:
        return f"No receipts for run {transcript.run_id}."
    lines = [f"Replay of {transcript.run_id} ({transcript.step_count} step(s)):"]
    for step in transcript.steps:
        approval = f" apv={step.approval_id}" if step.approval_id else ""
        lines.append(
            f"  seq={step.seq:>3} {step.ts} {step.tool} → {step.decision}"
            f"{approval} {step.hash[:16]}…"
        )
    return "\n".join(lines)
