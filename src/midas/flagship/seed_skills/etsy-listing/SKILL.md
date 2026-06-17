# etsy-listing — Etsy product listing draft

**When to use.** The operator wants to publish (or refresh) an Etsy listing
for a handmade or digital product.

**Inputs.**
- Product name + 1-sentence description
- Target buyer persona
- Hero image path (already drafted via `image.draft`)
- Price (USD)

**What to draft.**
1. `product.draft` — title (≤140 chars), audience, problem solved,
   deliverables (3–5 bullets), price.
2. `adcopy.draft` — 3 variants: 1 short (≤80 chars), 1 medium (≤200), 1 long
   description (≤500). Used for the Etsy listing fields.
3. `artifact.text` to `drafts/etsy/<slug>/seo-tags.md` — 13 SEO tags, each
   ≤20 chars, ordered by buyer intent (specific → broad).

**Honest constraints.**
- Etsy bans AI-generated images for "handmade" categories. If the hero comes
  from `image.draft` with provider=openai, the listing MUST go in
  "Digital Downloads" instead.
- Never copy competitor descriptions. Each variant is original to the
  operator's actual product.
- Tags must be terms a buyer would type. No filler ("nice", "great").
