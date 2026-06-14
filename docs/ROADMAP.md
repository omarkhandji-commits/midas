# MIDAS — Build plan (V0 → V3)

Principle: ship the smallest version that produces real value, then add autonomy only after
the safety layer for that autonomy exists. Never add capability faster than you add control.

## V0 — Scaffold & manual operator (DONE / today)
- **Features:** operating contract, system prompt, full architecture, scoring engine spec,
  security model, roadmap. Run manually in Claude Code; outputs a scored Opportunity Report.
- **Tools:** Claude Code, local files, web search, your existing skills.
- **Deliverables:** this repo. A scored shortlist on demand.
- **Timeline:** today. **Priority:** P0.
- **Risks:** none material (read/draft only).
- **Tests:** run "daily opportunity scan" → get a /100 shortlist with sourced claims.

## V1 — Semi-auto daily loop (Week 1–2)
- **Features:** Scout + Market + Competitor + Strategist + CFO + Landing/Copy + Outreach
  (draft only) + Metrics. SQLite memory. **Telegram approve/reject.** Spend caps + auto-halt.
  Append-only audit log. Daily morning/afternoon/evening workflow.
- **Tools:** SQLite (+sqlite-vec), Telegram bot, Brave/SearXNG search, gh CLI (read), Gmail draft.
- **Deliverables:** a daily scored pipeline, one deliverable/day, a working approval gate.
- **Timeline:** 1–2 weeks. **Priority:** P0.
- **Risks:** prompt injection via fetched content (mitigated: content-as-data, egress allow-list);
  approval fatigue (mitigated: batch approvals, clear one-line summaries).
- **Tests:** an outbound action is *always* blocked until approved; a cap breach halts + alerts;
  audit log hash-chain verifies.

## V2 — Provider-agnostic + desktop dashboard (Week 3–6)
- **Features:** **LiteLLM** router (any LLM API, cheap-by-default escalation). **Tauri desktop
  dashboard** (extremely simple: pipeline, P&L, approval queue, kill switch). Scheduled
  autonomous runs. Full Sentinel two-key gate. Learns-from-decisions memory. Simple CRM.
  Extract the orchestrator so it runs **without** Claude Code (standalone for GitHub users).
- **Tools:** LiteLLM, Tauri, OS scheduler/cron, Notion/SQLite CRM.
- **Deliverables:** a one-click desktop app non-devs can run; provider config screen; daily
  autonomous run with mobile approvals.
- **Timeline:** 3–6 weeks. **Priority:** P1.
- **Risks:** packaging/security of a desktop app (mitigated: signed builds, no host mounts,
  secrets in OS keychain); model-routing cost surprises (mitigated: hard caps enforced in router).
- **Tests:** swap provider in config with zero code change; desktop kill switch freezes a run;
  scheduled run respects caps and queues approvals.

## V3 — Full business operator (Month 2–3)
- **Features:** multi-project portfolio with per-project P&L; launch automation (gated steps);
  self-improvement (the Curator tunes scoring weights from outcomes); a **vetted marketplace of
  safe skills** the agent can request to install (install = approval-gated); public GitHub
  release with docs + onboarding.
- **Tools:** everything above + skill registry + CI secret scanning.
- **Deliverables:** a repeatable money machine; public 1.0 release; onboarding for general public.
- **Timeline:** 6–10 weeks. **Priority:** P2.
- **Risks:** marketplace = supply-chain risk (mitigated: signed, reviewed, sandboxed skills,
  human approval to install — never auto-install); scope creep (mitigated: each new capability
  ships with its control).
- **Tests:** end-to-end — opportunity → build plan → gated launch → first tracked revenue,
  with a clean audit trail and no un-approved outbound action anywhere in the chain.

## Milestones
- After V1: first opportunity taken from scan → drafted offer → (approved) outreach.
- After V2: first autonomous day with mobile approvals, zero surprise spend.
- After V3: trajectory toward **\$1,000 MRR**, then **\$3,000 MRR**, on a repeatable loop.
