# Security Release Notes

This file tracks release-hardening details that complement `docs/SECURITY.md`
and `docs/THREAT_MODEL.md`.

## Approval Integrity

- Default MIDAS planner tools queue the planned approval payload, not raw kwargs.
- Approval records carry risk, estimated cost, and expiry metadata.
- The exact payload remains unchanged so downstream hash checks stay honest.
- File-writing executors re-plan before execution and reject `sha256_new` or
  `sha256_prev` drift.
- `code.run` recalculates the approved code hash at execution time.

## Taint And Injection

- Agent loop taint is sticky. UNTRUSTED outputs remain UNTRUSTED in later tool
  calls.
- Fetched web pages, PDFs, emails, and third-party MCP/tool outputs are data,
  not instructions.
- The lethal-trifecta guard denies risky combinations of private data,
  untrusted input, and egress.

## Budget

- Budgeting supports task, day, month, skill, and persona scopes.
- `BudgetFuse.project()` exposes upfront spend projection before a run.

## Skills

- Skill manifests include `sha256`, permissions, source, path, risk, tags,
  enabled state, and review timestamp.
- Skill bodies are loaded only on demand.
- Remote skill sources are approval-only and are not downloaded silently.

## Media

- Offline media drafts produce approval-gated bytes.
- `remotion.project.draft` produces a real ZIP payload containing a minimal
  Remotion project.
- Cloud/provider generation remains explicit and operator-controlled.
