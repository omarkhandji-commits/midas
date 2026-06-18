"""course.outline_draft — structured outline + refusal contracts."""

from __future__ import annotations

import pytest

from midas.flagship.agent.tools.course import (
    CourseError,
    plan_course_outline,
)


def test_basic_outline_has_n_modules():
    out = plan_course_outline(
        topic="Sourdough bread mastery for beginners",
        audience="home bakers with no prior experience",
        n_modules=5,
    )
    assert len(out.modules) == 5
    assert out.modules[0].index == 1
    assert "Sourdough" in out.markdown


def test_objectives_appear_in_markdown():
    out = plan_course_outline(
        topic="Sourdough bread mastery for beginners",
        audience="home bakers",
        n_modules=3,
        learning_objectives=["Bake a crusty loaf", "Maintain a starter"],
    )
    assert "Bake a crusty loaf" in out.markdown
    assert "Maintain a starter" in out.markdown


def test_custom_titles_mark_needs_research():
    out = plan_course_outline(
        topic="Sourdough bread mastery for beginners",
        audience="home bakers",
        n_modules=3,
        module_titles=["Wild yeast biology", "Hydration ratios", "Crumb structure"],
    )
    assert all(m.needs_research for m in out.modules)


def test_default_shape_titles_used_when_none_supplied():
    out = plan_course_outline(
        topic="Sourdough bread mastery for beginners",
        audience="home bakers",
        n_modules=3,
    )
    assert out.modules[0].title == "Foundations"
    assert out.modules[1].title == "Core mechanic"


def test_refuses_thin_topic():
    with pytest.raises(CourseError, match="too thin"):
        plan_course_outline(
            topic="bake", audience="me", n_modules=3,
        )


def test_refuses_empty_audience():
    with pytest.raises(CourseError, match="non-empty audience"):
        plan_course_outline(
            topic="Sourdough bread mastery", audience="   ", n_modules=3,
        )


def test_refuses_too_few_modules():
    with pytest.raises(CourseError, match="≥2"):
        plan_course_outline(
            topic="Sourdough bread mastery", audience="bakers", n_modules=1,
        )


def test_refuses_over_cap():
    with pytest.raises(CourseError, match="capped at 20"):
        plan_course_outline(
            topic="Sourdough bread mastery", audience="bakers", n_modules=21,
        )


def test_module_titles_mismatch_refused():
    with pytest.raises(CourseError, match="has 2 entries"):
        plan_course_outline(
            topic="Sourdough bread mastery",
            audience="bakers",
            n_modules=3,
            module_titles=["A", "B"],
        )


def test_sha256_intent_changes_with_topic():
    a = plan_course_outline(
        topic="Sourdough bread mastery", audience="bakers", n_modules=2,
    )
    b = plan_course_outline(
        topic="Pasta from scratch", audience="bakers", n_modules=2,
    )
    assert a.sha256_intent != b.sha256_intent


def test_late_modules_marked_needs_research():
    out = plan_course_outline(
        topic="Sourdough bread mastery", audience="bakers", n_modules=10,
    )
    # Default shape positions 7+ are flagged for research depth.
    assert out.modules[6].needs_research
