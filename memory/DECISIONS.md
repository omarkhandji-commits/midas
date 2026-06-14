# MIDAS — Decision memory

The agent reads this before proposing and updates it after every approve/reject. It is how
MIDAS learns the operator's taste. Keep newest at top.

## Locked decisions (from setup, 2026-06-13)
- **Autonomy:** semi-auto = **approval-default** (locked, Proof-First contract). Research /
  analysis / scoring / drafting = automatic; outbound & irreversible actions = human approval.
  `full-auto-guarded` exists only as an explicit opt-in for power users, never the default.
  (policy.yml + models.py default + .env.example all aligned to semi-auto.)
- **Model posture:** provider-agnostic — must work with any LLM API (OpenAI, Anthropic,
  Mistral, Groq, Nous/Hermes, local Ollama). Cheap-by-default, escalate for stakes.
- **Channels:** Telegram + desktop interface + CLI (non-developers must be able to run it).
- **Audience:** general public, open-source on GitHub. Targets everyone, not one operator.
- **Posture:** security-first (default-deny, two-key approval, spend caps, audit log) and
  token-economical above all.
- **Revenue goal:** \$1,000 MRR → then \$3,000 MRR, via a repeatable money machine.

## Taste log (approve / reject history)
> (empty — fills as the operator approves or rejects proposals)

| Date | Proposal | Decision | Why | Weight nudge |
|------|----------|----------|-----|--------------|
|      |          |          |     |              |
