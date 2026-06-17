# cold-outreach-sequence — 5-step B2B outreach sequence

**When to use.** The operator has identified an ICP (ideal customer
profile) and wants a deliverability-aware sequence to test it.

**Pre-flight.**
- Run `email.deliverability_check` on the operator's sending domain.
  Score < 70 → STOP. Surface the recommendations and tell the operator
  to fix DNS before sending — landing in spam wastes the warm list.

**Inputs.**
- ICP: industry + role + company size + 1 trigger event
- Offer: 1 sentence
- Sending domain
- Up to 10 prospects (CSV of name, email, company)

**What to draft.**
1. `outreach.sequence` — 5 steps:
   - Step 1 (day 0): pattern-interrupt opener, ≤80 words, ends with a
     soft yes/no question (not a meeting ask).
   - Step 2 (+3d): value drop — 1 specific insight the prospect's
     trigger event makes relevant. Cite a source.
   - Step 3 (+7d): case-study-shaped — "a [similar role] at [similar
     company] achieved [outcome]". Don't fabricate; if no real case,
     drop this step.
   - Step 4 (+12d): direct ask, ≤40 words, single-question close.
   - Step 5 (+20d): break-up — "I'll close the loop; happy to reconnect
     when timing is better."
2. `email.draft` x 5 — one per step, addressed to ICP placeholder.
3. `artifact.text` to `drafts/outreach/<campaign>/sending-plan.md` —
   throttle plan: ≤20 sends/day for the first 5 business days, +20/day
   each subsequent week up to 200/day. This is warmup, not throttling
   for throttling's sake.

**Honest constraints.**
- NO purchased lists. Operator confirms each prospect has a
  legitimate reason to receive cold mail (downloaded a lead magnet,
  attended an event, fits a documented ICP).
- NO fake personalization ("noticed you went to X school" when
  scraped). If the personalization isn't specific to that prospect's
  actual situation, drop it.
- Unsubscribe link in EVERY step. CAN-SPAM, CASL, GDPR all require it.
- If the deliverability check returned warnings, surface them in the
  final email body comment so the operator sees them again.
