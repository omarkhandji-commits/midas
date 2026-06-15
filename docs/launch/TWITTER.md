# Launch thread — Twitter/X (do NOT post until repo is public)

## Tweet 1 (hook)

> Every AI agent demo ends with "look, it sent the email."
>
> MIDAS demos end with: *fifteen emails did not send because you didn't tap approve.*
>
> Open source. Hash-chained signed receipts. Verifier you can run with 100 lines of Python.
>
> 🧵

## Tweet 2 (the moat)

> Every tool call writes an Ed25519-signed, hash-chained receipt.
>
> A 100-line standalone verifier reads your ledger with **only `pynacl` installed** — no MIDAS trust required.
>
> Tamper one byte → caught at the corrupted `seq`.
>
> Spec: docs/RECEIPT_V1.md (frozen v1 with test vectors).

## Tweet 3 (the constraint)

> Approval-default isn't a setting. It's a structural invariant.
>
> Outbound sends, refunds, irreversible actions — all enter an ApprovalQueue.
> Human approves from dashboard, Telegram, Slack, Discord, WhatsApp, Email, or SMS.
>
> No "full auto" toggle bypasses it. By design.

## Tweet 4 (the budget)

> The budget fuse fires **before** the call, not after.
>
> Reserve → check cap → execute. A runaway loop can't blow past your monthly cap because
> the next call literally never reaches the model.
>
> Per-task / daily / monthly all enforced atomically.

## Tweet 5 (the proof)

> 9 Proof-First evals run on every commit, deterministic + offline:
>
> – fake-source clamping
> – unsourced claims downgrade
> – budget fuse raises BEFORE call
> – lethal trifecta = DENY
> – context compression fidelity
> – asset quality (no AI slop)
> – web research (no HIGH without verified sources)
> – τ-bench rule adherence (100% refusal of forbidden actions)
> – operator autonomy guardrails

## Tweet 6 (the disclaimer / honesty)

> I don't claim MIDAS is "secure" or "compliant" — those are organizational claims.
>
> The code does what it does. The spec is public. The receipts verify.
>
> Alpha; breaking changes possible until 1.0.

## Tweet 7 (CTA)

> Local-first. Provider-agnostic (local Ollama or cloud). Loopback-only dashboard. Zero telemetry.
>
> github.com/<owner>/<repo>
>
> Show HN coming this week.

---

**Posting notes:**
- Schedule Tweet 1 for 09:30 ET, then 90 sec between subsequent tweets.
- Replace `<owner>/<repo>` with real handle.
- Pin Tweet 1 for at least 7 days.
