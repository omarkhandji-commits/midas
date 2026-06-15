# Show HN draft — MIDAS

**Title:** `Show HN: MIDAS – business agent with hash-chained, independently verifiable receipts`

**Body (≤2,500 chars):**

I built MIDAS because every agent demo I've seen handwaves the part that actually
matters in business: *did this thing do what it said it did, can I prove it later,
and what stopped it from doing the thing I never wanted it to do?*

MIDAS is a local-first business operator for founders, consultants, agencies, and
small teams. It prepares revenue moves — research, ICP, drafts, outreach copy, PDFs
— and stops before any outbound action so the human approves and ships. That part
isn't novel.

What's novel are three things sitting under it:

1. **Receipt v1, a public spec for verifiable execution.** Every tool call writes a
   signed, hash-chained JSONL receipt. I shipped a 100-line standalone verifier
   (`pip install pynacl`, then `python -m midas_verify <ledger> --public-key <hex>`)
   that imports nothing from MIDAS itself. If you can't trust the runtime, you can
   re-verify the chain. There are deterministic test vectors in `docs/RECEIPT_V1.md`.

2. **Approval-default as a structural invariant**, not a setting. Outbound sends,
   payments, irreversible cancellations — these enter an `ApprovalQueue` and a human
   resolves them from the dashboard, Telegram, Slack, Discord, WhatsApp, SMS, or
   email. There is no "full auto" toggle that bypasses the queue.

3. **A budget fuse that reserves before it spends.** Caps fire BEFORE the model
   call, not after, so you cannot blow past a per-task / daily / monthly cap on a
   runaway loop.

Stack is Python 3.11+, FastAPI dashboard on loopback (no CDN, no telemetry, strict
CSP), provider-agnostic LLM router (local Ollama or any cloud), receipt signing via
Ed25519 (PyNaCl) with the secret in the OS keychain.

Quality bar I hold myself to: ruff + mypy strict + import-linter + bandit + pytest
all green every commit, and an in-repo eval suite (`midas eval`) that proves nine
Proof-First invariants on deterministic, offline inputs — including a τ-bench-style
rule-adherence test that demands 100% refusal of forbidden actions.

The "moat" is the spec, not the code. If you implement Receipt v1 in another agent,
my verifier reads your ledger. That's the goal.

Honest disclosures: alpha, breaking changes possible until 1.0, I don't claim
"secure" or "compliant" anywhere in the repo (those are organizational claims, not
cryptographic ones).

Repo: https://github.com/<owner>/<repo>
Spec: https://github.com/<owner>/<repo>/blob/main/docs/RECEIPT_V1.md
Verifier: https://github.com/<owner>/<repo>/tree/main/tools/verify

Happy to take questions on the threat model, the eval suite, or where the spec
needs sharpening for v2.

---

**Posting notes (do NOT publish until ready):**
- Replace `<owner>/<repo>` with the real GitHub path.
- Post at 09:00 ET on a Tuesday/Wednesday for best HN front-page odds.
- Have screenshots of the dashboard + a 90s loom of demo 1 ready in the first reply.
- Do not link the demo videos in the OP — keep them for the comment thread to bait
  click-through.
- Skip the "I made this in a weekend" framing — emphasize the spec.
