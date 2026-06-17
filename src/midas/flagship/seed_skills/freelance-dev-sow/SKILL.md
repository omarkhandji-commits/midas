# freelance-dev-sow — Freelance dev statement of work

**When to use.** A potential client wants a fixed-scope software project and
needs a one-page SOW before they sign + pay deposit.

**What to draft.**
1. `proposal.draft` — client, project name, scope as ≤5 bullet points, price,
   timeline, currency.
2. `quote.draft` — same client, line items (design, build, QA, deployment).
   Line totals must add up to the proposal price.
3. `stripe.payment_link` — 50% deposit. Description: `<project> — 50% deposit`.
4. `email.draft` — addressed to the client, with all three artifacts attached
   conceptually + the payment link in the body.

**Honest constraints.**
- Never invent capabilities the operator hasn't confirmed. If the operator
  hasn't done React Native before, the SOW says "web only".
- Price must come from the operator's stated rate × estimated days. No
  upselling.
- Deposit terms in plain language: "50% to start, 50% on delivery; refundable
  pro-rata if scope is cancelled before kickoff."
