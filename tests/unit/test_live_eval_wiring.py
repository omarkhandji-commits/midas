"""WS5 — Live eval lane wiring: builds, runs offline (fallback), reports."""

from __future__ import annotations

from midas.flagship.eval.live_eval import build_live_suite


def test_build_live_suite_constructs_without_model_call() -> None:
    """Suite construction must not contact Ollama (lazy LLM call)."""
    s = build_live_suite(model="gemma4:12b", host="http://127.0.0.1:0")
    assert s.evals
    assert "live" in s.name.lower()
    # Eval object must carry a name + callable .run.
    assert callable(s.evals[0].run)


def test_live_suite_falls_back_to_reference_when_ollama_unreachable() -> None:
    """If the Ollama HTTP endpoint isn't reachable, we use midas_reference_decide.

    That ensures the lane produces meaningful numbers (matching the offline
    reference) instead of silently passing or crashing. The test points at a
    closed port so the fetch will fail fast.
    """
    s = build_live_suite(model="gemma4:12b", host="http://127.0.0.1:1")
    results = s.run()
    assert results, "live suite must produce at least one EvalResult"
    er = results[0]
    # The reference policy passes all cases by construction.
    assert er.rate >= 0.85
    # At least the Pass@1 + adherence headline cases plus 7 detail cases.
    assert er.total >= 9
