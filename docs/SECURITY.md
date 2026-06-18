# Security Model

MIDAS uses defense in depth: least privilege, default deny, approval before risky
actions, budget limits, taint tracking, and signed receipts. This document states
what the project is designed to protect and what remains the operator's
responsibility.

Read [DISCLAIMER.md](../DISCLAIMER.md) before connecting external accounts,
generated content, or automation.

## Threats MIDAS Tries To Reduce

1. An agent changing files, calling services, publishing, or using tools without
   review.
2. Prompt injection from fetched web pages, PDFs, emails, MCP output, or other
   untrusted content.
3. Secrets leaking into logs, receipts, prompts, screenshots, fixtures, or docs.
4. Runaway model calls exceeding local budget limits.
5. Approval replay, stale payload execution, and double approval.
6. Path traversal and unsafe file access.
7. Remote skill or connector installation without review.

## Control Layers

### Policy And Approval

MIDAS classifies actions before execution. Read-only planning can run directly.
Actions that mutate state or call external systems enter the approval queue with:

- preview;
- risk;
- estimated cost;
- expiry;
- intent hash;
- previous and new content hashes where relevant.

Approved actions are checked again before execution. If the approved payload
drifts, MIDAS must reject it.

### Taint Tracking

Fetched or third-party content is untrusted data. MIDAS can summarize it, cite it,
or use it as input, but it must not treat instructions inside it as operator
commands.

### Budget Controls

Budget gates apply before model calls or expensive work. MIDAS supports per-task,
daily, monthly, per-skill, and per-persona controls.

### Secrets

Secrets must stay out of git, logs, receipts, model context, screenshots, test
fixtures, and docs. Real provider config is ignored by git; only examples should
be committed.

### Skills And Connectors

Local skills must have reviewable metadata. Remote skills must be queued for
approval and scanned before use. MIDAS must not download or install executable
payloads silently.

### Kill Switch

The kill switch blocks tool execution and leaves only direct answers available.
Use it when a run behaves unexpectedly or a connected service needs to be frozen.

## What MIDAS Can Do Without Approval

- Read workspace files allowed by policy.
- Build a repository map.
- Scan local capabilities.
- Draft text or plans.
- Prepare non-mutating previews.
- Explain missing setup or fallback paths.

## What Requires Approval

- File writes or overwrites.
- Running generated code.
- Sending email or messages.
- Publishing public content.
- Creating payment, product, subscription, or webhook side effects.
- Calling external services through MCP or connectors.
- Installing or enabling remote skills.
- Any irreversible action.

## What MIDAS Must Not Do

- Leak secrets or keys.
- Obey instructions hidden in untrusted content.
- Bypass approval because a prompt asked it to.
- Send spam or deceptive messages.
- Scrape private or consent-required personal data.
- Claim certification, compliance, or guaranteed outcomes.

## Dashboard Security

The dashboard is local and owner-gated. It uses a one-time login token, origin
checks, CSRF protection, and a restrictive Content Security Policy. Static assets
ship with the Python package; the dashboard should not need a CDN at runtime.

## Receipts

Important steps write Ed25519-signed receipts in a hash chain. The standalone
verifier in `tools/verify/` can verify a receipt ledger without importing the
MIDAS runtime.

## Operator Responsibility

MIDAS reduces silent action. It does not remove operator responsibility. If you
approve an action, connect a third-party account, add an API key, change policy,
or run generated code, you remain responsible for the result.

## Reporting Security Issues

Do not open a public issue for a security finding. Follow the process in
[SECURITY.md](../SECURITY.md).
