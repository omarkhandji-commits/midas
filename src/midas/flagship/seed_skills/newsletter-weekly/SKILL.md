# newsletter-weekly — Weekly newsletter draft

**When to use.** The operator runs a content-driven business (consultant,
creator, indie SaaS) and wants a draft issue ready to send.

**Inputs.**
- Topic / theme for the week
- Audience persona (1 sentence)
- 1–3 sources the operator has already read this week (links)

**What to draft.**
1. `artifact.text` to `drafts/newsletter/YYYY-MM-DD.md` — Markdown body with:
   - Hook (1–2 sentences, no clickbait)
   - 3 short sections, each with 1 specific insight + 1 source link
   - CTA: link to the operator's product / consult page / payment link
2. `email.draft` — subject ≤ 60 chars, plain-text first paragraph, the
   Markdown rendered as HTML in body.

**Honest constraints.**
- No "guaranteed", "secret", "you won't believe" wording.
- Every claim cites a source. If a section has no source, drop it.
- Maximum length 500 words — readers leave after that.
