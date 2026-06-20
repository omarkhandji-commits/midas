# Channel setup — every provider, step by step

MIDAS bridges approvals to whichever channel you live in. **Telegram** uses
long-polling (no extra setup beyond a bot token). **Email** is pull-based — MIDAS
reads your inbox when an agent step calls `email.inbox.read`. The other four
(Discord, Slack, WhatsApp, SMS) are **webhook-based**: the provider POSTs to a
URL MIDAS exposes.

> **Loopback constraint.** MIDAS binds to `127.0.0.1:8765` by design. Webhook
> channels cannot work out-of-the-box because providers cannot reach your
> laptop from the public internet. Use a tunnel like
> [ngrok](https://ngrok.com/), [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/),
> or [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) to expose the
> dashboard. Telegram and Email do not need a tunnel.

---

## ngrok in 60 seconds (any webhook channel)

```bash
# Once, on your machine:
brew install ngrok                          # or: choco install ngrok
ngrok config add-authtoken <token-from-ngrok-dashboard>

# Each time you want to receive webhooks:
ngrok http 8765
```

ngrok prints a `https://xxxx.ngrok-free.app` URL. **That** is your tunnel base.
The webhook URL you paste into each provider becomes:

| Channel | Webhook URL |
|---|---|
| Discord | `https://xxxx.ngrok-free.app/api/webhooks/discord` |
| Slack | `https://xxxx.ngrok-free.app/api/webhooks/slack` |
| WhatsApp | `https://xxxx.ngrok-free.app/api/webhooks/whatsapp` |
| SMS (Twilio) | `https://xxxx.ngrok-free.app/api/webhooks/sms` |

Stop ngrok → webhooks stop working. Restart ngrok → URL changes (free plan) →
update each provider with the new URL.

---

## Telegram (no tunnel needed)

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, choose name + username
2. Copy the bot token
3. Talk to [@userinfobot](https://t.me/userinfobot), `/start` → it returns your numeric chat ID
4. In MIDAS `/connections`: paste the bot token + chat ID

The Telegram listener starts automatically with `midas dashboard` (no extra
command needed). Send any message to your bot → MIDAS replies with the pending
approval queue.

---

## Discord

**Discord uses Ed25519 signatures via a *separate* application public key.** The
bot token sends messages; the public key verifies inbound interactions.

1. https://discord.com/developers/applications → New Application
2. Bot → Reset Token → copy as `bot_token`
3. General Information → copy **Public Key** as `DISCORD_PUBLIC_KEY`
4. Set Interactions Endpoint URL to `https://xxxx.ngrok-free.app/api/webhooks/discord` and Save (Discord pings the endpoint to verify the public key is right)
5. In MIDAS `/connections`: paste the bot token + your Discord user ID
6. Save the public key in the keychain (UI add-key path) under handle `DISCORD_PUBLIC_KEY`

Note: PyNaCl is required (`pip install pynacl`). If it's not installed, the
endpoint rejects every Discord call with `401 invalid signature`.

---

## Slack

**Slack uses HMAC-SHA256 signatures via the app's Signing Secret.**

1. https://api.slack.com/apps → Create New App → From scratch
2. Basic Information → copy **Signing Secret** as `SLACK_SIGNING_SECRET`
3. OAuth & Permissions → Install to Workspace → copy Bot User OAuth Token
4. Interactivity & Shortcuts → on → Request URL = `https://xxxx.ngrok-free.app/api/webhooks/slack`
5. In MIDAS `/connections`: paste the bot token + your Slack user ID
6. Save the signing secret in the keychain under handle `SLACK_SIGNING_SECRET`

---

## WhatsApp (Meta Cloud API)

**Meta uses HMAC-SHA256 of the body with the App Secret (not the access token).**

1. https://developers.facebook.com/apps → Create App → Business → next
2. Add **WhatsApp** product
3. API Setup → copy a 24h test access token (or generate a permanent one)
4. App Settings → Basic → copy **App Secret** as `WHATSAPP_APP_SECRET`
5. Webhooks → Configure URL = `https://xxxx.ngrok-free.app/api/webhooks/whatsapp` + a verify token you make up (save it as `WHATSAPP_VERIFY_TOKEN`)
6. Subscribe to the `messages` field
7. In MIDAS `/connections`: paste access_token + owner_phone + phone_number_id
8. Save app secret + verify token in the keychain under their handles

---

## SMS (Twilio)

**Twilio uses HMAC-SHA1 of the URL+sorted params, signed with the auth token.**

1. https://console.twilio.com → buy a number with SMS capability
2. Number → Messaging → A MESSAGE COMES IN → Webhook = `https://xxxx.ngrok-free.app/api/webhooks/sms` (POST)
3. Account info → copy Account SID + Auth Token
4. In MIDAS `/connections`: paste account_sid + auth_token + from_number + your phone

Twilio will sign every incoming SMS with the auth token. MIDAS verifies and
replies in TwiML (XML format Twilio expects).

---

## Email (no tunnel needed)

Email is on-demand only — MIDAS reads your inbox via IMAP **when an agent step
calls `email.inbox.read`**. There is no background listener.

1. In MIDAS `/connections`: enter your email address
2. (Optional) Add IMAP host/user/pass for non-Gmail/Outlook providers
3. Use the `email.inbox.read` tool in a mission — MIDAS connects, reads unread
   messages flagged as leads, and surfaces them in `/leads`

For outbound, MIDAS drafts every email through the approval queue. Configure
SMTP credentials in `/settings` to enable actual sending after approval.

---

## Verifying it works

After ngrok is running and the provider is wired:

1. Send a test message from the channel to MIDAS
2. Open `/approvals` — you should see the message handled (approve/reject button reply)
3. Check `/proofs` — every webhook hit emits a receipt (`webhook.<channel>` tool, ALLOW or DENY)

If the receipt shows DENY with `reason: signature_mismatch`, the secret in the
keychain doesn't match what the provider sent. Re-copy the secret from the
provider's dashboard.
