# MIDAS Threat Model

## Assets

- API keys and local secrets.
- Customer and business data.
- Approval authority.
- Payment, posting, messaging, CRM, and repository access.
- Proof ledger and memory.
- Operator reputation.

## Main Threats

| Threat | Defense |
|---|---|
| Prompt injection from web/PDF/media | untrusted taint, source verification, Sentinel gate |
| Secret exfiltration | secrets broker, no raw secret receipts, egress approval |
| Approval bypass | single approval queue, owner checks, dashboard CSRF/origin checks |
| Token/cost runaway | budget fuse, routing, cache, run modes |
| Fake ROI or fake sources | cite-or-abstain, verifier, evals |
| Supply-chain skill attack | manifest, static scan, denied executables, remote approval |
| Unsafe cron automation | recipe generation only; user installs manually |
| Ledger tampering | signed hash-chained receipts |

## Non-Goals

- MIDAS is not a compliance product.
- MIDAS does not certify legal, financial, tax, or security correctness.
- MIDAS does not guarantee platform deliverability or business results.

## Required Invariant

Any action that can harm money, accounts, reputation, customers, legal posture, or local
files must pass through approval unless the operator has explicitly changed policy.
