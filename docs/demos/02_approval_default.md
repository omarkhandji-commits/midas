# Demo 2 — Approval-default in action (≤90 s)

**One-line hook.** *MIDAS prepares 20 cold emails. The budget meter ticks live.
The operator approves only 5 from their phone. Exactly 5 send, 15 stay drafts.*

## Why this demo

Every other agent demo cuts at "look, it sent the email." MIDAS demo ends with
**"15 emails did not send because you didn't tap approve."** That's the product.

## Pre-roll setup (off-camera)

1. `midas up` running on a laptop. Dashboard open at `http://127.0.0.1:8765`.
2. Telegram bot connected (token already in keychain, owner_chat_id set).
3. A demo niche / ICP loaded into memory so the run produces a real draft set.

## Storyboard

| 0:00–0:06 | Title: **"You approve. MIDAS executes. Never the other way around."** |
| 0:06–0:20 | Run `midas scan "boutique law firms in Montreal"` from a terminal. The dashboard ticks up: budget meter climbs $0.00 → $0.07. Research sources cited live. |
| 0:20–0:35 | Asset Studio panel: 20 outreach emails drafted, each with a `{{first_name}}` placeholder. No PII fabricated. Approval-card stack of 20 appears in the Approvals page. |
| 0:35–0:50 | Operator picks up phone. Telegram message: "20 outreach drafts queued. Reply with ids to approve." Operator taps **Approve** on 5 cards (visible inline_keyboard). Rejects nothing — just doesn't approve the other 15. |
| 0:50–1:05 | Back on dashboard: 5 approvals resolved → 5 emails actually sent (mocked SMTP for demo). The other 15 visibly stay in "pending" status, never sent. |
| 1:05–1:15 | Closing card: **"Approval-default holds. The agent prepares; the human ships."** |

## Voice-over script

> Twenty cold emails, drafted in fifteen seconds. Watch what doesn't happen next.
>
> The agent is done. The drafts are ready. Personalization is templated — never
> scraped from the web. Now it stops and waits.
>
> Twenty approval cards arrive on the operator's phone. Five get tapped.
>
> Five emails go out. Fifteen don't. The agent never overrides me, and there is
> no auto-execute mode that breaks this rule.

## Captions

- `0:20` — *"Budget fuse: caps reserved BEFORE the call, not after."*
- `0:35` — *"Phone approve from Telegram, Discord, Slack, WhatsApp, Email, SMS."*
- `1:05` — *"Approval-default: a structural invariant, not a setting you can toggle off."*

## Assets

- Two devices: laptop (dashboard) + phone (Telegram). Use OBS scene mix.
- Mock SMTP — never send real emails in a recording.

## Editor notes

- Show the dashboard's **green badge ledger entries** matching every approval.
- Avoid stock outreach copy — use a sober B2B offer. (No "10x your revenue".)
