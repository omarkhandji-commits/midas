"""Voice and phone-call planning with approval-first defaults."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class VoiceDraft:
    channel: str
    text: str
    ssml: str
    approval_required: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CallPlan:
    contact_label: str
    purpose: str
    script: str
    consent_required: bool = True
    opt_out_required: bool = True
    approval_required: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def draft_voice_message(text: str, *, channel: str = "voice_note") -> VoiceDraft:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        raise ValueError("voice message text cannot be empty")
    ssml = f"<speak>{_escape_ssml(cleaned)}</speak>"
    return VoiceDraft(channel=channel, text=cleaned, ssml=ssml)


def plan_call(*, contact_label: str, purpose: str, offer: str) -> CallPlan:
    if not contact_label.strip() or not purpose.strip():
        raise ValueError("contact_label and purpose are required")
    script = (
        f"Purpose: {purpose.strip()}\n\n"
        "Opening: Hi, this is a short business call. Is now an okay time?\n"
        "Consent: If not, I can stop here and not contact you again.\n"
        f"Context: I wanted to ask about {offer.strip()}.\n"
        "Question: Is this problem active for you right now?\n"
        "Close: If useful, I can send a written summary for you to review."
    )
    return CallPlan(contact_label=contact_label.strip(), purpose=purpose.strip(), script=script)


def _escape_ssml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
