"""Persona presets — opinionated starter configs for common operator profiles.

Why
---
Telling someone new "the agent has 25 tools" is overwhelming. Telling them
"I see you're a freelance dev — here's the SOW skill, here's how to send a
50% deposit link, here's where leads land" is actionable. Personas are the
opinionated bridge.

Each persona names: a tagline (one sentence), a suggested first action
(verbatim — the wizard can drop it into the chat), a small set of
recommended skills (already shipped in seed_skills/), and the operator's
default currency. Nothing here egresses, nothing reads secrets — pure data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Persona:
    """One operator profile. ``id`` is stable for the API; everything else
    is a hint the wizard surfaces to the new user."""

    id: str
    label: str
    tagline: str
    first_action: str  # ready to paste into the chat as a starting prompt
    recommended_skills: list[str]
    default_currency: str  # USD, EUR, CAD, GBP, JPY


_PRESETS: tuple[Persona, ...] = (
    Persona(
        id="freelance_dev",
        label="Freelance developer",
        tagline="Quote new projects fast, collect deposits without chasing.",
        first_action=(
            "Draft a 1-page SOW + a 50% deposit payment link for a "
            "$3,000 React landing page project, then queue the client email."
        ),
        recommended_skills=["freelance-dev-sow"],
        default_currency="USD",
    ),
    Persona(
        id="consultant",
        label="Independent consultant",
        tagline="Turn discovery calls into signed proposals the same day.",
        first_action=(
            "Draft a proposal + quote for a 6-week brand strategy "
            "engagement at $12,000, include a 30% deposit Stripe link."
        ),
        recommended_skills=["freelance-dev-sow"],
        default_currency="USD",
    ),
    Persona(
        id="content_creator",
        label="Content creator / newsletter",
        tagline="Ship a weekly issue with sources, attribution, and a CTA.",
        first_action=(
            "Draft this week's newsletter on the topic of "
            "<paste your topic>; pull 3 sources you've already read, "
            "end with a link to my consult page."
        ),
        recommended_skills=["newsletter-weekly"],
        default_currency="USD",
    ),
    Persona(
        id="ecommerce_etsy",
        label="E-commerce / Etsy seller",
        tagline="Publish listings that read like a buyer, not a coder.",
        first_action=(
            "Draft an Etsy listing for a $49 hand-illustrated digital "
            "wedding invitation: product copy + 3 ad-copy variants + 13 SEO tags."
        ),
        recommended_skills=["etsy-listing"],
        default_currency="USD",
    ),
    Persona(
        id="local_business",
        label="Local business (bakery, salon, gym, …)",
        tagline="Catch local intent on Google, Instagram, and word-of-mouth.",
        first_action=(
            "Draft a landing page + 3 Instagram captions for a Saturday "
            "promotion at my Montréal bakery (custom cakes, order by Thursday)."
        ),
        recommended_skills=[],
        default_currency="CAD",
    ),
)


def list_personas() -> list[Persona]:
    """Return the full preset list. Stable order for the API."""
    return list(_PRESETS)


def find_persona(persona_id: str) -> Persona | None:
    for p in _PRESETS:
        if p.id == persona_id:
            return p
    return None


def persona_as_dict(p: Persona) -> dict[str, object]:
    """JSON-friendly shape for the API."""
    return asdict(p)
