# MIDAS — Architecture

## 1. Name
**MIDAS** (recommended). Alternatives, all easy to swap (it's just a folder name today):
- **MINT** — consumer-friendly, "mint cash", works as a verb.
- **FOUNDRY** — "where companies are forged"; builder connotation.
- **RAINMAKER** — the business term for someone who brings in revenue.
- **OPERATOR** / **CASHOPS** — descriptive, ops-flavored.
- **HELIOS / KAIROS** — premium, abstract (Kairos = "the opportune moment").

Why MIDAS: instantly understood (Midas touch → turns work into gold/cash), premium,
memorable for a general-public open-source release, pairs perfectly with the mission.

## 2. Mission (one line)
> Find, build, launch and sell the most profitable opportunities — with the least support
> and the least risk — and stay accountable in cash.

## 3. Sub-agents
Each sub-agent has the **least-privilege** tool set it needs and nothing more. The
**Sentinel** wraps all of them: any outbound/irreversible action is intercepted and queued
for human approval. Autonomy column = behavior at the default `semi-auto` setting.

| # | Sub-agent | Role | Inputs | Outputs | Tools | Autonomy | Approval? |
|---|-----------|------|--------|---------|-------|----------|-----------|
| 1 | **Scout** | Find opportunities, pain points, "people complain but nobody builds it" | search queries, niches, operator notes | ranked opportunity candidates + sources | web search, read-only fetch | Auto | No |
| 2 | **Market Analyst** | Size demand, trends, willingness to pay | candidate | demand brief + confidence | search, trends data | Auto | No |
| 3 | **Competitor Analyst** | Map competitors, pricing, gaps | candidate | competitor table + the gap | search, read-only fetch | Auto | No |
| 4 | **Strategist** | Synthesize → pick niche + define the offer | briefs above | one-page offer + positioning | LLM (smart) | Auto | No |
| 5 | **Revenue Analyst (CFO)** | Score /100, build ROI + P&L, enforce caps | offer + costs | score breakdown, P&L, go/no-go | scoring engine, memory | Auto | No |
| 6 | **Builder / Code Planner** | Turn the pick into a build plan + Codex/Claude/Cursor prompts | chosen project | build plan + ready prompts + repo plan | files (local), git (read) | Auto (plan); repo writes | **Yes** to write/push |
| 7 | **Landing & Copy** | Landing page, pricing page, offer copy | offer | draft pages/copy (local) | files, LLM | Auto (draft) | **Yes** to publish |
| 8 | **Outreach** | Find leads *legally*, draft messages/emails/posts | ICP, offer | prospect list + drafts (unsent) | search, files | Auto (draft) | **Yes** to send/contact |
| 9 | **SEO / Content** | SEO plan, content, programmatic pages | niche, keywords | content drafts + SEO plan | search, files | Auto (draft) | **Yes** to publish |
| 10 | **Launch** | Orchestrate the launch checklist | go decision | launch plan + gated steps | coordinates others | Auto (plan) | **Yes** per external step |
| 11 | **Support Minimizer** | Design to reduce support; FAQ, docs, self-serve | product spec | support-reduction plan, FAQ/docs | LLM, files | Auto | No |
| 12 | **Metrics** | KPIs, dashboard data, weekly/monthly report | all activity | KPI report + dashboard feed | memory, files | Auto | No |
| 13 | **Sentinel (Guardian)** | Enforce gates, spend caps, audit log, prompt-injection defense, kill switch | every action request | allow / queue-for-approval / deny + audit entry | policy engine, audit log | Always-on | Is the gate |
| 14 | **Curator (Memory)** | Maintain decision memory + learn taste from approve/reject | decisions | updated DECISIONS / PNL / PIPELINE | memory | Auto | No |

Mapping to the classic agent zoo you listed: Scout = Research/Prospection-research,
Market+Competitor = market/competitor analysts, Strategist = Product Strategist, **CFO =
the missing piece most agents lack**, Builder = Code Planner/GitHub agent, Landing/Copy +
SEO + Outreach = marketing/growth/outreach agents, Launch = launch agent, Metrics = metrics
agent, **Sentinel = the safety layer almost no open agent ships**, Curator = the memory the
others forget.

## 4. Daily / weekly / monthly workflow
- **Morning (scan):** Scout → Market/Competitor refresh → Revenue Analyst re-scores the
  pipeline → output a 3-line *"today's best revenue move"*.
- **Afternoon (execute one move):** the relevant sub-agent produces ONE concrete
  deliverable. Anything outbound goes to the approval queue.
- **Evening (close the loop):** Metrics updates KPIs, Curator logs decisions + taste, P&L
  updated, tomorrow's move proposed.
- **Weekly (portfolio):** kill <60 scores, double down on winners, KPI report, pricing check.
- **Monthly (strategy):** MRR vs. milestone, new bets, retire dead projects, cost review.

## 5. Scoring
See [`SCORING.md`](SCORING.md). Final score /100; <60 archive, 60–74 watchlist, 75+ build.

## 6. Recommended stack (free / low-cost)
| Layer | Pick | Notes |
|---|---|---|
| Runtime (now) | **Claude Code** sub-agents + skills + slash commands | zero infra, cheapest tokens, you already have it |
| Runtime (later) | extract to a small **Python** orchestrator (LangGraph or a plain loop) | for standalone GitHub users without Claude Code |
| LLM routing | **LiteLLM** (provider-agnostic) | OpenAI, Anthropic, Mistral, Groq, Together/Nous-Hermes, **Ollama** local |
| Cheap model | local **Ollama** (Llama 3.x / Qwen) or Groq free tier | high-volume, low-stakes |
| Smart model | Claude Sonnet / GPT-class | high-stakes only |
| Memory (structured) | **SQLite** (+ `sqlite-vec` for semantic recall) | projects, scores, P&L, approvals, leads |
| Memory (notes) | local **Markdown** vault (+ optional Obsidian read) | human-readable decision log |
| Files / VCS | local repo + **git**, **gh** CLI | writes gated |
| Search | **Brave Search API** free tier / **SearXNG** self-host / DuckDuckGo | robots-respecting only |
| Email | Gmail API **draft-only** | sending gated |
| CRM | SQLite `leads` table or **Notion** | simple, free |
| Tasks | local `tasks.json` or Notion board | |
| Logs | append-only **JSONL** audit (hash-chained) + git history | tamper-evident |
| Dashboard | **Tauri** desktop app (small, secure) or localhost web UI | "extremely simple" for general public |
| Automation | OS scheduler / cron / Claude Code scheduled tasks | autonomous runs |
| Monitoring | spend tracker → **Telegram** alerts | surprise-bill protection |

## 7. Free tools by job
- **Market research:** Google Trends, Exploding Topics (free tier), Reddit/HN/forum search, app-store reviews.
- **Competitor analysis:** their pricing pages, BuiltWith free, SimilarWeb free tier, G2/Capterra reviews.
- **GitHub:** `gh` CLI, GitHub search, GitHub Actions free minutes.
- **Legal scraping:** robots-respecting fetch, public APIs, RSS — never gated/PII data.
- **Landing pages:** static HTML/CSS (you already ship these), Astro, GitHub Pages / Netlify / Vercel free tier.
- **SEO:** Google Search Console, Bing Webmaster, free keyword tools, schema.org markup.
- **Email:** Gmail (draft), free SMTP for transactional; deliverability checks before any send.
- **CRM:** Notion / SQLite.
- **Analytics:** Plausible self-host / Umami / GA4 free.
- **Docs:** Markdown, MkDocs.
- **Tests:** Playwright, Vitest/Pytest (free).
- **Video/demo:** OBS, free screen recorders.
- **Design:** local SVG, Canva free, your existing UI skills.
- **Deploy:** Netlify / Vercel / GitHub Pages / Cloudflare Pages free tiers (deploy gated).
- **Automation:** cron, n8n self-host, GitHub Actions.

## 8. Security & control
Full model in [`SECURITY.md`](SECURITY.md). Summary: default-deny, two-key approval for all
outbound/irreversible actions, least-privilege per sub-agent, hard spend caps with auto-halt,
hash-chained audit log, prompt-injection defenses (fetched content is data, never commands),
secrets in OS keychain / encrypted env (never committed), and a one-command kill switch.

## 9. Build plan
See [`ROADMAP.md`](ROADMAP.md) for V0 → V3 with features, tools, deliverables, timeline,
priority, risks and tests.

## 10. System prompt
See [`../agent/system-prompt.md`](../agent/system-prompt.md) — copy-paste ready.
