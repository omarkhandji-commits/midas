"""WS-Webhooks — signature verifiers for Slack, Twilio, Discord, WhatsApp.

We test the signature primitives directly. Integration with the dashboard
routes is exercised by the existing security suite once the wiring lands.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from midas.flagship.dashboard.webhooks import (
    verify_discord_signature,
    verify_slack_signature,
    verify_twilio_signature,
    verify_whatsapp_signature,
)

# ── Slack v0 HMAC-SHA256 ───────────────────────────────────────────────────


def _slack_sign(secret: str, ts: str, body: bytes) -> str:
    base = f"v0:{ts}:{body.decode('utf-8')}".encode()
    return "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


def test_slack_signature_accepts_fresh_signature() -> None:
    secret = "fake-signing-secret"
    body = b'{"action_id":"a"}'
    ts = str(int(time.time()))
    sig = _slack_sign(secret, ts, body)
    assert verify_slack_signature(body=body, timestamp=ts, signature=sig, signing_secret=secret)


def test_slack_signature_rejects_tampered_body() -> None:
    secret = "fake-signing-secret"
    body = b'{"action_id":"a"}'
    ts = str(int(time.time()))
    sig = _slack_sign(secret, ts, body)
    assert not verify_slack_signature(
        body=b'{"action_id":"different"}', timestamp=ts, signature=sig, signing_secret=secret
    )


def test_slack_signature_rejects_old_timestamp() -> None:
    secret = "fake-signing-secret"
    body = b'{}'
    ts = str(int(time.time()) - 10_000)  # 2h 47m old
    sig = _slack_sign(secret, ts, body)
    assert not verify_slack_signature(
        body=body, timestamp=ts, signature=sig, signing_secret=secret
    )


def test_slack_signature_rejects_empty_secret() -> None:
    assert not verify_slack_signature(
        body=b"", timestamp="0", signature="v0=00", signing_secret=""
    )


# ── Twilio HMAC-SHA1 ───────────────────────────────────────────────────────


def _twilio_sign(token: str, url: str, params: dict[str, str]) -> str:
    base = url
    for k in sorted(params):
        base += k + params[k]
    return base64.b64encode(
        hmac.new(token.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")


def test_twilio_signature_accepts_correct_signature() -> None:
    token = "fake-auth-token"
    url = "https://example.com/api/webhooks/sms"
    params = {"From": "+15551234567", "Body": "approve 42", "To": "+15557654321"}
    sig = _twilio_sign(token, url, params)
    assert verify_twilio_signature(
        url=url, form_params=params, signature=sig, auth_token=token
    )


def test_twilio_signature_rejects_tampered_params() -> None:
    token = "fake-auth-token"
    url = "https://example.com/api/webhooks/sms"
    params = {"From": "+15551234567", "Body": "approve 42"}
    sig = _twilio_sign(token, url, params)
    # Attacker flips the body but reuses the old signature.
    assert not verify_twilio_signature(
        url=url,
        form_params={"From": "+15551234567", "Body": "reject 42"},
        signature=sig,
        auth_token=token,
    )


# ── WhatsApp HMAC-SHA256 ───────────────────────────────────────────────────


def test_whatsapp_signature_accepts_correct() -> None:
    secret = "meta-app-secret"
    body = b'{"object":"whatsapp_business_account"}'
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_whatsapp_signature(
        body=body, signature_header=expected, app_secret=secret
    )


def test_whatsapp_signature_rejects_wrong_prefix() -> None:
    secret = "meta-app-secret"
    body = b"{}"
    bad = "sha1=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha1).hexdigest()
    assert not verify_whatsapp_signature(body=body, signature_header=bad, app_secret=secret)


def test_whatsapp_signature_rejects_empty_secret() -> None:
    assert not verify_whatsapp_signature(body=b"x", signature_header="sha256=abc", app_secret="")


# ── Discord Ed25519 ────────────────────────────────────────────────────────


@pytest.mark.skipif(
    pytest.importorskip("nacl", reason="PyNaCl optional dep absent") is None,
    reason="nacl missing",
)
def test_discord_signature_accepts_correct_signature() -> None:
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    public_key_hex = signing_key.verify_key.encode().hex()
    timestamp = "1719999999"
    body = b'{"type":1}'
    signed = signing_key.sign(timestamp.encode("utf-8") + body)
    sig_hex = signed.signature.hex()
    assert verify_discord_signature(
        body=body, timestamp=timestamp, signature_hex=sig_hex, public_key_hex=public_key_hex
    )


def test_discord_signature_rejects_empty_inputs() -> None:
    assert not verify_discord_signature(
        body=b"x", timestamp="", signature_hex="abc", public_key_hex="abc"
    )
