# MIDAS — Autonomous Revenue Operator

> Find, build, launch and sell the most profitable opportunities — with the least
> support and the least risk — and stay accountable in **cash**, not busywork.

MIDAS is an open-source autonomous business agent. Unlike task-loop agents that burn
tokens and ship nothing, MIDAS is **revenue-accountable**: every action carries an
expected ROI and a hard cost budget, it keeps a live P&L, and it refuses work that
doesn't ladder to money. It is **provider-agnostic** (any LLM API — OpenAI, Anthropic,
Mistral, Groq, Nous/Hermes, local Ollama), **safe by default** (nothing leaves your
machine without a one-tap human approval), and reachable from **Telegram, desktop, and
CLI** so non-developers can run it too.

---

## Why MIDAS exists (the gap)

The existing agent landscape splits into three buckets, and every bucket has the same
complaint attached to it:

| Tool family | What people complain about |
|---|---|
| AutoGPT / BabyAGI / dev loops | "It looped, burned \$ in API calls, and produced nothing sellable." |
| Manus / Devin / closed SaaS | "I can't trust a black box with my accounts, my money, my repo — and it's expensive." |
| Generic assistants (Hermes, etc.) | "It chats and researches, but it has no business accountability and no memory of my taste." |

**Nobody ships an agent that is all of these at once:** open-source **+** provider-agnostic
**+** cost-capped **+** revenue-accountable **+** safe-by-default **+** usable by a non-developer
from their phone. That is the gap MIDAS fills.

## The five differentiators

1. **Revenue-accountable, not task-accountable.** Expected-ROI tag + token budget on every
   action. Live P&L. Refuses busywork. → kills "it spent money and made nothing".
2. **Two-key safety (the Vault gate).** Default-deny. Email, posting, deploys, payments,
   repo writes and file deletes all require an explicit human Approve (one tap in Telegram).
   Append-only, hash-chained audit log. → kills "I'm scared to give it access".
3. **Provider-agnostic + cost-capped.** Any LLM API. Cheap model by default, strong model
   only for high-stakes calls. Hard daily / per-task spend caps with auto-halt. → kills the
   surprise bill.
4. **Reachable everywhere.** Telegram bot + desktop app + CLI. → non-devs can run it.
5. **Learns your taste.** Every approve/reject is stored and feeds future scoring. → sharper
   every week.

## Hard rules (non-negotiable)

No spam · no scams · no false promises · no guaranteed-income claims to customers · no mass
sending without approval · no payment without approval · no deletion/modification of critical
files without approval · no marketing lies · no high-support traps · no needless complexity.

The agent is **autonomous to analyze, compare, draft and propose**. It must get human
approval before any **outbound or irreversible** action. See [`docs/SECURITY.md`](docs/SECURITY.md).

## Status

**V0 — scaffold.** This repo currently contains the operating contract, the system prompt,
the full architecture, the scoring engine spec, the security model, and the build roadmap.
See [`docs/ROADMAP.md`](docs/ROADMAP.md) for V0 → V3.

## Repo map

```
midas/
├─ README.md                 ← you are here
├─ CLAUDE.md                 ← operating contract for the agent runtime
├─ agent/system-prompt.md    ← the full, copy-paste system prompt
├─ docs/ARCHITECTURE.md      ← sub-agents, daily workflow, stack, free tools
├─ docs/SECURITY.md          ← threat model, two-key gate, spend caps, audit log
├─ docs/SCORING.md           ← the /100 opportunity score
├─ docs/ROADMAP.md           ← V0 → V3 build plan
├─ config/policy.yml         ← autonomy gates, spend caps, allow/deny lists
├─ config/providers.example.yml ← provider-agnostic LLM routing
└─ memory/                   ← decision memory, P&L, leads (gitignored)
```

## Quickstart (V0, manual)

1. Copy `.env.example` → `.env` and fill at least one LLM provider key.
2. Open this folder in Claude Code (or your agent runtime).
3. Paste [`agent/system-prompt.md`](agent/system-prompt.md) as the system prompt.
4. Ask: *"Run a daily opportunity scan and give me a scored shortlist."*

> ⚠️ Never commit `.env` or anything in `memory/`. The `.gitignore` already blocks them.

## License

MIT (intended). Use legally and ethically. MIDAS does not guarantee income.
