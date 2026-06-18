"""blog.seo_lint — checklist scoring on markdown posts."""

from __future__ import annotations

from midas.flagship.agent.tools.blog_seo import lint_blog

_GOOD_BODY = (
    "# A complete guide to homemade kombucha brewing in small batches\n\n"
    + "Body paragraph. " * 100
    + "\n\n## Why home brewing matters\n\n"
    + "More body. " * 80
    + "\n\n[Related: bottling guide](./bottling)\n\n"
    + "![Kombucha jar with SCOBY](/img/scoby.jpg)\n"
)


def test_well_formed_post_scores_high():
    res = lint_blog(
        markdown=_GOOD_BODY,
        title="A complete guide to homemade kombucha brewing techniques",
        meta_description=(
            "Step-by-step instructions for brewing kombucha at home, "
            "from first SCOBY to second fermentation. Includes a checklist."
        ),
    )
    assert res.score >= 90
    assert res.h1_count == 1
    assert res.images_missing_alt == 0
    assert res.internal_links >= 1


def test_missing_title_is_high_severity():
    res = lint_blog(markdown="# H1\n\nBody.")
    codes = [i.code for i in res.issues]
    assert "missing_title" in codes
    high = [i for i in res.issues if i.code == "missing_title"]
    assert high[0].severity == "high"


def test_title_too_long_flagged():
    res = lint_blog(
        markdown="# H1\n\n" + "body. " * 100,
        title="A" * 80,
        meta_description="x" * 100,
    )
    codes = [i.code for i in res.issues]
    assert "title_too_long" in codes


def test_multiple_h1_flagged():
    res = lint_blog(
        markdown="# First\n\nBody.\n\n# Second\n\nMore.",
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
    )
    codes = [i.code for i in res.issues]
    assert "multiple_h1" in codes


def test_heading_skip_flagged():
    res = lint_blog(
        markdown="# H1\n\nBody.\n\n### H3 skip\n\n" + "body " * 100,
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
    )
    codes = [i.code for i in res.issues]
    assert "heading_skip" in codes


def test_thin_content_flagged():
    res = lint_blog(
        markdown="# H1\n\nShort body.",
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
    )
    codes = [i.code for i in res.issues]
    assert "thin_content" in codes


def test_image_missing_alt_flagged():
    md = (
        "# H1\n\n"
        + "body " * 100
        + "\n\n![](/img/no-alt.jpg)\n\n[Link](/x)\n"
    )
    res = lint_blog(
        markdown=md,
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
    )
    codes = [i.code for i in res.issues]
    assert "image_missing_alt" in codes
    assert res.images_missing_alt == 1


def test_frontmatter_provides_title():
    md = (
        "---\n"
        'title: "A reasonable length title for the SEO post here"\n'
        'description: "' + "y" * 100 + '"\n'
        "---\n"
        "# H1\n\n"
        + "body " * 100
        + "\n\n[Link](/x)\n"
    )
    res = lint_blog(markdown=md)
    assert "reasonable length title" in res.title


def test_internal_vs_external_links():
    md = (
        "# H1\n\n"
        + "body " * 100
        + "\n\n[Internal](/about) [External](https://example.com)\n"
    )
    res = lint_blog(
        markdown=md,
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
        site_domain="kenzassweet.ca",
    )
    assert res.internal_links == 1
    assert res.external_links == 1


def test_site_domain_matches_external_to_internal():
    md = (
        "# H1\n\n"
        + "body " * 100
        + "\n\n[On site](https://kenzassweet.ca/cakes)\n"
    )
    res = lint_blog(
        markdown=md,
        title="A reasonable length title for the SEO post here",
        meta_description="x" * 100,
        site_domain="kenzassweet.ca",
    )
    assert res.internal_links == 1
    assert res.external_links == 0


def test_score_floors_at_zero():
    res = lint_blog(markdown="bad")
    assert res.score >= 0


def test_non_string_rejected():
    import pytest

    with pytest.raises(TypeError, match="string"):
        lint_blog(markdown=123)  # type: ignore[arg-type]
