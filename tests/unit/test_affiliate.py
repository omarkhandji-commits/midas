"""affiliate.link.generate — URL validation, UTM build, anti-overwrite."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from midas.flagship.agent.tools.affiliate import (
    AffiliateError,
    generate_affiliate_link,
)


def test_basic_link_adds_utms() -> None:
    link = generate_affiliate_link(
        merchant_url="https://shop.example.com/p/widget",
        campaign="march-sale",
    )
    q = parse_qs(urlparse(link.url).query)
    assert q["utm_source"] == ["midas"]
    assert q["utm_medium"] == ["referral"]
    assert q["utm_campaign"] == ["march-sale"]
    assert link.merchant == "shop.example.com"
    assert link.campaign == "march-sale"
    assert len(link.sha256) == 64


def test_preserves_existing_non_utm_params() -> None:
    link = generate_affiliate_link(
        merchant_url="https://shop.example.com/p/x?ref=newsletter&color=red",
        campaign="spring",
    )
    q = parse_qs(urlparse(link.url).query)
    assert q["ref"] == ["newsletter"]
    assert q["color"] == ["red"]
    assert q["utm_campaign"] == ["spring"]


def test_refuses_existing_utm_to_avoid_silent_override() -> None:
    with pytest.raises(AffiliateError, match="already carries"):
        generate_affiliate_link(
            merchant_url="https://shop.example.com/p/x?utm_source=other",
            campaign="x",
        )


def test_refuses_non_http_url() -> None:
    with pytest.raises(AffiliateError, match="absolute http"):
        generate_affiliate_link(merchant_url="ftp://shop/x", campaign="x")


def test_refuses_empty_campaign() -> None:
    with pytest.raises(AffiliateError, match="non-empty campaign"):
        generate_affiliate_link(
            merchant_url="https://shop.example.com/", campaign="   "
        )


def test_extra_params_cannot_override_utm() -> None:
    with pytest.raises(AffiliateError, match="overrides reserved"):
        generate_affiliate_link(
            merchant_url="https://shop.example.com/",
            campaign="x",
            extra_params={"utm_source": "evil"},
        )


def test_extra_params_pass_through() -> None:
    link = generate_affiliate_link(
        merchant_url="https://shop.example.com/",
        campaign="x",
        extra_params={"ref_code": "ABC123"},
    )
    q = parse_qs(urlparse(link.url).query)
    assert q["ref_code"] == ["ABC123"]


def test_optional_content_and_term() -> None:
    link = generate_affiliate_link(
        merchant_url="https://shop.example.com/",
        campaign="launch",
        content="banner",
        term="bakery owner",
    )
    q = parse_qs(urlparse(link.url).query)
    assert q["utm_content"] == ["banner"]
    assert q["utm_term"] == ["bakery_owner"]


def test_sha256_changes_with_url() -> None:
    a = generate_affiliate_link(
        merchant_url="https://shop.example.com/a",
        campaign="c",
    )
    b = generate_affiliate_link(
        merchant_url="https://shop.example.com/b",
        campaign="c",
    )
    assert a.sha256 != b.sha256
