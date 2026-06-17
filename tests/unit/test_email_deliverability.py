"""email.deliverability_check — parsers + scorer + input validation.

The DNS path itself is mocked via _txt_query — the unit tests verify
the policy logic without hitting the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from midas.flagship.agent.tools.email_deliverability import (
    DeliverabilityError,
    DkimRecord,
    DmarcRecord,
    SpfRecord,
    _compute_score,
    _parse_dmarc,
    _parse_spf,
    check_deliverability,
)


def test_parse_spf_detects_minus_all() -> None:
    rec = _parse_spf(["v=spf1 include:_spf.google.com -all"])
    assert rec.found is True
    assert rec.has_minus_all is True
    assert rec.notes == []


def test_parse_spf_warns_on_soft_fail() -> None:
    rec = _parse_spf(["v=spf1 include:mailgun.org ~all"])
    assert rec.found is True
    assert rec.has_minus_all is False
    assert any("soft fail" in n for n in rec.notes)


def test_parse_spf_missing() -> None:
    assert _parse_spf(["irrelevant txt"]).found is False
    assert _parse_spf([]).found is False


def test_parse_dmarc_reject_policy() -> None:
    rec = _parse_dmarc(
        ["v=DMARC1; p=reject; rua=mailto:dmarc@example.com; pct=100"]
    )
    assert rec.found is True
    assert rec.policy == "reject"
    assert rec.has_rua is True
    assert rec.pct == 100
    assert rec.notes == []


def test_parse_dmarc_warns_on_none_policy() -> None:
    rec = _parse_dmarc(["v=DMARC1; p=none"])
    assert rec.policy == "none"
    assert any("quarantine" in n.lower() for n in rec.notes)


def test_parse_dmarc_warns_on_partial_pct() -> None:
    rec = _parse_dmarc(["v=DMARC1; p=reject; pct=10"])
    assert rec.pct == 10
    assert any("pct=10" in n for n in rec.notes)


def test_compute_score_strong_setup() -> None:
    score, recs = _compute_score(
        SpfRecord(found=True, has_minus_all=True),
        DkimRecord(found=True, selectors_found=["google"]),
        DmarcRecord(found=True, policy="reject", has_rua=True, pct=100),
    )
    assert score == 100
    assert recs == []


def test_compute_score_nothing_published() -> None:
    score, recs = _compute_score(
        SpfRecord(found=False),
        DkimRecord(found=False),
        DmarcRecord(found=False),
    )
    assert score == 0
    assert any("SPF" in r for r in recs)
    assert any("DKIM" in r for r in recs)
    assert any("DMARC" in r for r in recs)


def test_compute_score_dmarc_none_loses_strict_bonus() -> None:
    score, recs = _compute_score(
        SpfRecord(found=True, has_minus_all=True),
        DkimRecord(found=True, selectors_found=["x"]),
        DmarcRecord(found=True, policy="none", has_rua=False, pct=100),
    )
    # SPF 35 + DKIM 30 + DMARC found 20 = 85 (no strict-policy +10, no rua +5)
    assert score == 85
    assert any("p=quarantine" in r for r in recs)
    assert any("rua=" in r for r in recs)


def test_check_deliverability_rejects_empty_domain() -> None:
    with pytest.raises(DeliverabilityError, match="real domain"):
        check_deliverability("   ")


def test_check_deliverability_rejects_url() -> None:
    with pytest.raises(DeliverabilityError, match="bare domain"):
        check_deliverability("https://example.com")


def test_check_deliverability_uses_mocked_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test the full path with a fake _txt_query."""

    fake: dict[str, list[str]] = {
        "good.example": ["v=spf1 include:_spf.google.com -all"],
        "_dmarc.good.example": ["v=DMARC1; p=reject; rua=mailto:r@good.example"],
        "google._domainkey.good.example": [
            "v=DKIM1; k=rsa; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQ..."
        ],
    }

    def _fake(name: str) -> list[str]:
        return fake.get(name, [])

    monkeypatch.setattr(
        "midas.flagship.agent.tools.email_deliverability._txt_query", _fake
    )

    report = check_deliverability("good.example")
    assert report.spf.found and report.spf.has_minus_all
    assert report.dmarc.found and report.dmarc.policy == "reject"
    assert report.dkim.found and "google" in report.dkim.selectors_found
    assert report.score == 100
    assert report.proof_level == "MEDIUM"


def test_check_deliverability_accepts_custom_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def _fake(name: str) -> list[str]:
        seen.append(name)
        return []

    monkeypatch.setattr(
        "midas.flagship.agent.tools.email_deliverability._txt_query", _fake
    )
    check_deliverability("example.com", dkim_selectors=["customsel"])
    assert "customsel._domainkey.example.com" in seen
    # Must NOT have probed the default 'google' selector for example.com.
    assert "google._domainkey.example.com" not in seen


def _unused_any() -> Any:  # ensure typing import is used
    return None
