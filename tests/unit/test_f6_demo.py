"""Sprint F6 — offline planner produces an artifact end-to-end."""

from __future__ import annotations

from pathlib import Path

from midas.flagship.agent.loop import (
    AgentTranscript,
    offline_artifact_planner,
)


def test_offline_planner_proposes_artifact_first(tmp_path: Path) -> None:
    plan = offline_artifact_planner("Test task", AgentTranscript(task="Test task"))
    assert plan["tool"] == "artifact.text"
    assert plan["inputs"]["path"] == "do-output.md"
    assert "Test task" in plan["inputs"]["content"]


def test_offline_planner_returns_done_after_first_step() -> None:
    transcript = AgentTranscript(task="x")
    transcript.steps.append(
        type(  # quick dataclass-shaped stub
            "S",
            (),
            {
                "tool": "artifact.text",
                "decision": "queue_approval",
                "ran": False,
                "approval_id": 1,
                "inputs": {},
                "output_summary": "",
                "error": None,
            },
        )()
    )
    plan = offline_artifact_planner("x", transcript)
    assert plan == {"done": True, "summary": "offline planner: one artifact then done"}
