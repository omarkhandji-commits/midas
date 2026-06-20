"""WS-Webhooks — POST /api/webhooks/{discord,slack,whatsapp,sms} routes.

Each provider speaks a different webhook protocol with its own signature scheme:

- **Slack**: HMAC-SHA256 of ``v0:<ts>:<body>`` signed with the signing secret.
- **Twilio (SMS)**: HMAC-SHA1 of ``<url><sorted form params concatenated>`` signed
  with the auth token, base64.
- **Discord**: Ed25519 of ``<ts><body>`` verified with the application's public
  key (a *different* credential than the bot token). Requires PyNaCl.
- **Meta WhatsApp**: HMAC-SHA256 of the raw body signed with the app secret.

All four routes are wired here; signature verification happens BEFORE the
existing channel handlers parse the payload. Every route emits a receipt
through the dashboard's ledger so unauthorized hits are auditable.

These routes are loopback-only by default like the rest of the dashboard.
Production use needs a public tunnel (ngrok / Cloudflare Tunnel / Tailscale
Funnel) so the providers can reach ``/api/webhooks/<channel>``. The UI on
/channels carries that note explicitly — no silent "should just work".
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import parse_qsl

from starlette.requests import Request
from starlette.responses import Response

# Vault handles for verification credentials (separate from the bot tokens used
# to send messages — different scopes per provider).
SLACK_SIGNING_SECRET = "SLACK_SIGNING_SECRET"
TWILIO_AUTH_TOKEN_HANDLE = "SMS_AUTH_TOKEN"
DISCORD_PUBLIC_KEY = "DISCORD_PUBLIC_KEY"
WHATSAPP_APP_SECRET = "WHATSAPP_APP_SECRET"


def _json(code: int, body: dict) -> Response:
    return Response(
        content=json.dumps(body), status_code=code, media_type="application/json"
    )


def verify_slack_signature(
    *,
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
    max_skew_seconds: int = 60 * 5,
) -> bool:
    """Slack v0 HMAC-SHA256 check.

    Returns False if the signing secret is empty, the timestamp is too old, or
    the signature does not match. Constant-time comparison.
    """
    if not signing_secret or not signature or not timestamp:
        return False
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False
    import time

    if abs(time.time() - ts_int) > max_skew_seconds:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8', errors='replace')}".encode()
    expected = (
        "v0="
        + hmac.new(signing_secret.encode("utf-8"), sig_basestring, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def verify_twilio_signature(
    *,
    url: str,
    form_params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    """Twilio HMAC-SHA1 check.

    Twilio concatenates URL + sorted form params (key then value, no separator)
    and signs with the account auth token; base64-encoded.
    """
    if not auth_token or not signature:
        return False
    base = url
    for key in sorted(form_params):
        base += key + form_params[key]
    expected = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def verify_whatsapp_signature(
    *, body: bytes, signature_header: str, app_secret: str
) -> bool:
    """Meta WhatsApp HMAC-SHA256 check.

    Header format: ``X-Hub-Signature-256: sha256=<hex>``. App secret is on the
    Meta App settings page, separate from the access token.
    """
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def verify_discord_signature(
    *, body: bytes, timestamp: str, signature_hex: str, public_key_hex: str
) -> bool:
    """Discord Ed25519 check using the application public key.

    Returns False if PyNaCl is unavailable, or any input is empty, or the
    signature does not verify. Discord application public key comes from the
    Developer Portal, *not* the bot token.
    """
    if not public_key_hex or not signature_hex or not timestamp:
        return False
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError:
        return False
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        message = timestamp.encode("utf-8") + body
        verify_key.verify(message, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


# ── Route registration ─────────────────────────────────────────────────────


def register_webhook_routes(app: Any, deps: Any) -> None:
    """Mount /api/webhooks/{discord,slack,whatsapp,sms} on the FastAPI app.

    `deps` is the DashboardDeps holding the channels manager and ledger. All
    routes return 401 on signature failure, 200 + handler reply on success.
    """

    def _receipt(channel: str, decision: str, reason: str) -> None:
        if deps.ledger is None:
            return
        try:
            from midas.core.receipts.models import Decision, Taint

            deps.ledger.append(
                run_id=f"webhook:{channel}",
                agent=f"channel-{channel}",
                tool=f"webhook.{channel}",
                decision=Decision.ALLOW if decision == "allow" else Decision.DENY,
                inputs={"reason": reason},
                outputs={},
                cost_usd=0.0,
                taint_in=Taint.UNTRUSTED,
                taint_out=Taint.UNTRUSTED,
            )
        except Exception:
            return

    @app.post("/api/webhooks/slack")
    async def webhook_slack(request: Request) -> Response:
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        body = await request.body()
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        signing_secret = deps.channels.vault.get(SLACK_SIGNING_SECRET) or ""
        if not verify_slack_signature(
            body=body, timestamp=timestamp, signature=signature, signing_secret=signing_secret
        ):
            _receipt("slack", "deny", "signature_mismatch")
            return _json(401, {"error": "invalid signature"})
        config = deps.channels.slack_config()
        if config is None:
            return _json(503, {"error": "slack not configured"})
        try:
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict):
                return _json(400, {"error": "json object required"})
        except ValueError:
            return _json(400, {"error": "invalid json"})
        from midas.flagship.channel_settings import SlackActionHandler

        handler = SlackActionHandler(config=config, queue=deps.queue)
        reply = handler.handle_action(payload)
        _receipt("slack", "allow", "signature_ok")
        return _json(200, {"text": reply})

    @app.post("/api/webhooks/sms")
    async def webhook_sms(request: Request) -> Response:
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        body = await request.body()
        signature = request.headers.get("X-Twilio-Signature", "")
        form_params = dict(
            parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        )
        url = str(request.url)
        auth_token = deps.channels.vault.get(TWILIO_AUTH_TOKEN_HANDLE) or ""
        if not verify_twilio_signature(
            url=url, form_params=form_params, signature=signature, auth_token=auth_token
        ):
            _receipt("sms", "deny", "signature_mismatch")
            return _json(401, {"error": "invalid signature"})
        config = deps.channels.sms_config()
        if config is None:
            return _json(503, {"error": "sms not configured"})
        from midas.flagship.channel_settings import SMSReplyHandler

        handler = SMSReplyHandler(config=config, queue=deps.queue)
        reply = handler.handle_message(
            from_phone=form_params.get("From", ""),
            body=form_params.get("Body", ""),
        )
        _receipt("sms", "allow", "signature_ok")
        return Response(
            content=f"<Response><Message>{reply}</Message></Response>" if reply else "<Response/>",
            media_type="application/xml",
            status_code=200,
        )

    @app.post("/api/webhooks/discord")
    async def webhook_discord(request: Request) -> Response:
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        body = await request.body()
        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        public_key = deps.channels.vault.get(DISCORD_PUBLIC_KEY) or ""
        if not verify_discord_signature(
            body=body, timestamp=timestamp, signature_hex=signature, public_key_hex=public_key
        ):
            _receipt("discord", "deny", "signature_mismatch_or_pynacl_missing")
            return _json(401, {"error": "invalid signature"})
        config = deps.channels.discord_config()
        if config is None:
            return _json(503, {"error": "discord not configured"})
        try:
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict):
                return _json(400, {"error": "json object required"})
        except ValueError:
            return _json(400, {"error": "invalid json"})
        # Discord PING (type 1) → just ACK
        if payload.get("type") == 1:
            _receipt("discord", "allow", "ping_ack")
            return _json(200, {"type": 1})
        from midas.flagship.channel_settings import DiscordInteractionHandler

        handler = DiscordInteractionHandler(config=config, queue=deps.queue)
        reply = handler.handle_interaction(payload)
        _receipt("discord", "allow", "signature_ok")
        return _json(200, {"type": 4, "data": {"content": reply}})

    @app.post("/api/webhooks/whatsapp")
    async def webhook_whatsapp(request: Request) -> Response:
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        body = await request.body()
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        app_secret = deps.channels.vault.get(WHATSAPP_APP_SECRET) or ""
        if not verify_whatsapp_signature(
            body=body, signature_header=signature_header, app_secret=app_secret
        ):
            _receipt("whatsapp", "deny", "signature_mismatch")
            return _json(401, {"error": "invalid signature"})
        config = deps.channels.whatsapp_config()
        if config is None:
            return _json(503, {"error": "whatsapp not configured"})
        try:
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict):
                return _json(400, {"error": "json object required"})
        except ValueError:
            return _json(400, {"error": "invalid json"})
        from midas.flagship.channel_settings import WhatsAppWebhookHandler

        handler = WhatsAppWebhookHandler(config=config, queue=deps.queue)
        reply = handler.handle_webhook(payload)
        _receipt("whatsapp", "allow", "signature_ok")
        return _json(200, {"reply": reply})

    @app.get("/api/webhooks/whatsapp")
    async def webhook_whatsapp_verify(request: Request) -> Response:
        """Meta verification handshake (GET with hub.challenge param)."""
        if deps.channels is None:
            return _json(503, {"error": "channels disabled"})
        mode = request.query_params.get("hub.mode", "")
        token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")
        expected = deps.channels.vault.get("WHATSAPP_VERIFY_TOKEN") or ""
        if mode == "subscribe" and expected and token == expected:
            return Response(content=challenge, media_type="text/plain", status_code=200)
        return _json(403, {"error": "verify token mismatch"})


__all__ = [
    "register_webhook_routes",
    "verify_slack_signature",
    "verify_twilio_signature",
    "verify_discord_signature",
    "verify_whatsapp_signature",
]
