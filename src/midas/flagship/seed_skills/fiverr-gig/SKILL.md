# fiverr-gig — Fiverr gig optimizer

**When to use.** The operator wants a new Fiverr gig that ranks for buyer
search terms in their category, or wants to refresh an underperforming one.

**Inputs.**
- Category + sub-category (e.g. "Programming & Tech → WordPress")
- Operator's actual skill / output (1 paragraph)
- Lowest starter package price + delivery days
- Hero image path (already drafted via `image.draft`)

**What to draft.**
1. `product.draft` — gig title (≤80 chars, must include 1 high-intent
   keyword from the buyer's search, NOT marketing fluff), audience,
   problem solved, 3-tier package deliverables (Basic / Standard /
   Premium), Basic price.
2. `adcopy.draft` — 3 description variants:
   - Variant A: bullet-led (5 bullets, ≤15 words each, scannable)
   - Variant B: story-led (200 words, hook + problem + outcome)
   - Variant C: FAQ-led (5 Q&A pairs anticipating buyer hesitation)
3. `artifact.text` to `drafts/fiverr/<slug>/tags.md` — 5 SEO tags
   (Fiverr's hard limit), ordered by buyer intent. Each tag ≤20 chars.

**Honest constraints.**
- Title: NO "professional", "high quality", "fast delivery" — every gig
  claims those and they don't rank. Use a concrete deliverable instead
  ("Will install + configure WooCommerce on your WordPress site").
- Pricing: Basic must be ≥ the operator's stated minimum; don't undercut
  to chase volume — Fiverr's algo penalizes cancellations.
- No fake reviews. The operator earns reviews by delivering.
- Tags: terms a buyer types, not adjectives. "wordpress plugin"
  beats "expert".
