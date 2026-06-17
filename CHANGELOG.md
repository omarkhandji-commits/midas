# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`web.scrape` tool — rendered fetch with honest anti-bot defenses.**
  Runs the page through a clean headless Chromium (Playwright) so the agent
  sees what a human would on JS-rendered sites (Etsy, Reddit, Fiverr,
  competitor blogs). ``http.fetch`` stays for static pages — ``web.scrape``
  is for the rest. Respects ``robots.txt`` by default; override requires
  ``allow_disallowed=True`` AND an explicit egress allowlist entry.
  Per-host rate limit (2s minimum), user-agent rotation through a real
  current-browser pool, viewport jitter, clean profile every call.
  Captcha markers (reCAPTCHA / hCaptcha / Cloudflare challenge) trigger a
  clean stop — never a bypass attempt. Output is ``Taint.UNTRUSTED`` and
  capped at 200 000 chars. Playwright is an optional dep; the error surfaces
  the install command when missing.
- **Skill loader on-demand (`skill.index` + `skill.load`).** Claude Code's
  token-economy pattern, ported. The planner sees only the *index* by
  default (one line per skill: name + 1-sentence summary), and pulls a
  specific body via ``skill.load(name)`` only when one matches the task.
  Body load is capped at 20 000 chars so a misconfigured skill can't blow
  the context. Both tools are AUTO-tier (``read_local_files``) — they read
  from the local skill registry, never egress, never run scripts. Installing
  a skill remains its own approval-gated flow.
- **Three seed cash-shaped skills** under
  ``src/midas/flagship/seed_skills/`` so the loader has real content out of
  the box: ``freelance-dev-sow`` (proposal + quote + 50% deposit Stripe link
  + client email), ``newsletter-weekly`` (weekly issue draft + send),
  ``etsy-listing`` (product + adcopy + SEO tags, with the honest constraint
  that AI-generated images go in Digital Downloads, not Handmade).
- **Stripe webhook receiver (`POST /api/webhooks/stripe`).** Closes the
  auto-attribution loop: when a payment succeeds, Stripe POSTs an event;
  MIDAS verifies the HMAC-SHA256 signature with constant-time compare,
  rejects events outside a 5-minute tolerance window (Stripe's recommended
  replay defense), parses the event, and writes a ``MemoryKind.CASH`` entry
  with the Stripe dashboard URL as a source. Idempotent on ``event.id`` —
  duplicate webhook replays are no-ops. The ONE unauthenticated endpoint in
  the dashboard, bound to loopback by design; the operator tunnels via
  ngrok/cloudflared to expose it. Atomic secret rotation (multiple ``v1=``
  sigs in one header) supported. Honest constraint: body parsing happens
  ONLY after the signature is verified.
- **Stripe payment link tool (`stripe.payment_link`).** Closes the cash loop —
  before this tool, the agent could draft a quote/proposal/invoice but had no
  way to collect the cash without manual operator work. The planner validates
  amount + currency + description against Stripe's per-currency minimum and
  stores the canonical intent (currency|amount_minor|product|description) in
  the approval payload with a sha256 hash. ``STRIPE_API_KEY`` is read only at
  execute time, never at plan time — an unapproved request can never reach
  Stripe. The implementation refuses publishable keys (``pk_…``) upfront with
  a clear message rather than letting Stripe return 401. Two backends ship:
  ``StubStripeBackend`` (deterministic, no egress) and ``StripeBackendImpl``
  (real REST calls to ``/v1/prices`` + ``/v1/payment_links``, form-encoded as
  the API expects). Failed link creation writes a ``DENY`` receipt — never
  silently dropped.
- **Social publish tool (`social.publish`).** Approval-gated, adapter-based.
  The planner validates platform / handle / text and resolves media paths
  through ``FsGuard`` — no credential read, no egress at plan time. The
  approval payload carries the canonical text + a ``sha256_intent`` of
  ``platform|handle|text|media``; the executor refuses to publish if that
  hash drifts between approval and execute (defense against payload tampering).
  Two adapters ship: ``StubSocialAdapter`` (no egress, deterministic
  ``post_id`` from sha256, for tests + dry-runs) and ``XTwitterAdapter``
  (opt-in, requires ``X_BEARER_TOKEN`` / ``TWITTER_BEARER_TOKEN``, calls X
  API v2). The executed receipt is tagged with ``platform`` + ``post_id``
  so ``compute_post_roi`` can join cost to revenue. Output is
  ``Taint.UNTRUSTED`` (third-party API response is data, not instructions).
  A failed publish writes a ``DENY`` receipt — failures are visible in the
  chain, never silently dropped. Adapters for LinkedIn / Instagram / YouTube
  drop into ``_ADAPTERS`` without API changes.
- **Image draft tool (`image.draft`).** Provider-agnostic, approval-gated. The
  planner produces PNG bytes at plan time and stores them base64-encoded in the
  approval payload, so the reviewer sees the exact sha256 before any write hits
  disk. Two backends ship: ``offline`` (deterministic Pillow placeholder, in the
  ``multimodal`` extra) and ``openai`` (opt-in, requires ``OPENAI_API_KEY`` —
  uses the operator's own key, never silent egress). The post-approval executor
  decodes bytes through the same ``execute_fs_write`` chokepoint every other
  artifact uses. Honest: the offline backend is a placeholder, not AI-generated
  — the rendered text on the canvas makes that unmistakable. New backends drop
  into ``_BACKENDS`` without API changes.
- **How-it-works page (`/how-it-works`).** A grand-public explainer in the
  dashboard: the 3-phrase contract (auto / approve / signed proof), a tour of
  every screen, side-by-side "what it can do" / "what it never does",
  collapsible FAQ, and a security summary. Pure React.
- **Unified Connections page (`/connections`).** One screen that summarizes the
  brain (LLM providers) and channels (Telegram/Discord/Slack/WhatsApp/Email/SMS)
  with readiness chips and deep-links to the existing manage pages. Reuses
  ``/api/providers`` + ``/api/channels``; no new endpoints.
- **Capabilities page.** A new `/capabilities` route lists every registered
  tool grouped by purpose (files, cash artifacts, code, research, MCP), with
  honest badges: AUTO vs APPROVE (read from the live policy), egress, and
  untrusted-output. The list is generated server-side from
  `build_default_toolset()` — adding a tool to the registry surfaces it in
  the UI without touching the front end. Backed by `GET /api/capabilities`.
- **Per-post ROI.** `compute_post_roi` joins receipts tagged with
  `platform` + `post_id` to operator-recorded outcomes keyed by
  `platform:post_id`. Cost still comes from the signed chain; revenue still
  comes only from outcomes — no projections. `build_post_outcomes_index`
  separates per-post keys from run-level keys so the two ledgers don't mix.
- **Browser opens already signed in.** `midas init` (and `midas dashboard`)
  now start the local console and open the browser on a magic sign-in link
  (single-use, loopback-only). No more terminal token to copy. `--no-launch`
  keeps the old behavior; `midas dashboard --show-link` prints the link in
  the rare case the browser doesn't open.
- **Interactive onboarding wizard.** The `/start` page is now a four-step
  guided flow: pick a model (Ollama detected automatically or paste a cloud
  key with the provider auto-inferred from the prefix), choose a notification
  channel, see how Midas works, run a first cash move — all without leaving
  the page. `GET /api/onboard/detect-ollama` and `GET /api/onboard/state`
  back the wizard.
- **Shared provider-defaults table** (`src/midas/flagship/provider_defaults.py`)
  mutualised between `midas init` and the dashboard's "add provider" flow,
  so the same default `cheap` model is picked through either surface.
- **One-command onboarding.** `midas init` detects a running local model
  (Ollama) or takes a single API key (provider inferred from the prefix:
  OpenAI, Anthropic, OpenRouter, Groq, Google), writes config and `.env`,
  initializes state, and runs a one-token smoke test.
- **Cash loop end-to-end.** `midas earn <niche>` chains discovery, scoring,
  asset preparation, and approval queuing in one cycle. `midas pipeline`
  surfaces every move's stage, derived from the receipt ledger, the approval
  queue, and recorded outcomes — no hidden state.
- **Six cash-shaped artifact tools.** `landing.draft`, `product.draft`,
  `outreach.sequence`, `proposal.draft`, `quote.draft`, `adcopy.draft`. All
  approval-gated; bytes live in the approval payload with sha256 of the
  proposed content.
- **Autonomous preparation pass.** `midas heartbeat "<n1,n2,…>"` prepares
  drafts across multiple niches behind hard caps (max niches, max artifacts,
  wall-clock budget). Never executes; only queues approvals.
- **Cash namespace in memory.** `MemoryKind.CASH` and `record_cash()` capture
  attributed revenue/cost per channel × offer. `context_pack(bias_kind=…)`
  surfaces it ahead of other memory in the planner prompt. Proof-First applies
  — sourced entries promote to MEDIUM; unsourced stay LOW.
- **Feedback edge.** `flows/feedback.py` derives a bounded factor-score
  adjustment (±2 per factor) from CASH/RESULT/ERROR memory and applies it
  before the next scan scores opportunities.
- **Vault advisor.** `midas advise <vault> --live` reads a Markdown vault
  (Obsidian-compatible), ranks three next moves citing source notes, and
  optionally launches a cash cycle on the top move (`--start`). Symlinks
  escaping the vault are rejected.
- **Model Context Protocol integration.** `midas mcp serve` exposes nine
  tools (six cash artifacts + pipeline/approvals/ROI reads) over stdio. Every
  mutating call returns an approval ticket instead of bytes. `midas mcp
  add | list | remove | test | import` manage external MCP servers; imported
  tools register under `mcp.<server>.<tool>` with `output_taint=UNTRUSTED`
  and live behind the `call_external_mcp` action (approval-gated).
- **Optional container sandbox for `code.run`.** When `podman` or `docker`
  is on PATH, executions run in a rootless container with `--net=none` and
  capabilities dropped. The result records the isolation tier ("process" or
  "container") in the receipt. The historical `-I -S` process sandbox remains
  the default fallback.
- **Live eval lane.** `midas eval --suite live` runs τ-bench cases against a
  real local model (Ollama by default). The offline deterministic suite
  remains the gate; the live lane is opt-in.

### Fixed

- **Provider key added in the dashboard now wires the cheap role.** Previously
  pasting a key in `/providers` stored it in the OS keychain but left the
  `cheap` role pointing elsewhere, so the agent silently kept using whatever
  default model `providers.yml` named — even when nothing was configured for
  it. `ProviderManager.add()` now writes `MIDAS_MODEL_CHEAP` to `.env` and
  mutates the in-process role on first usable key, and respects any explicit
  operator choice already in the environment.

### Changed

- `midas setup` seeds `config/providers.yml` from the example when missing.
- `midas memory add <kind>` accepts any case (`USER`, `user`, `User`) and
  suggests valid kinds on typo.
- `midas replay` with no argument lists every `run_id` known to the ledger.
- `pipeline` and `roi` truncate long `run_id` values on grapheme boundaries
  rather than cutting through UTF-8 sequences.

### Security

- New action `call_external_mcp` in `requires_approval`. Third-party MCP
  responses are tagged `Taint.UNTRUSTED`, so the lethal-trifecta rule fires if
  combined with private access plus egress.
- Obsidian vault scanner refuses symlinks whose resolved target escapes the
  vault.
- 17 additional invariant tests cover path traversal, kill switch under
  multiple paths, prompt-injection labelling, replay determinism, cash
  attribution strictness, and MCP prefix safety.

### Quality

- Test suite: 413 tests passing.
- Type-checked: 130 source files clean under `mypy`.
- Linted: `ruff` clean; `bandit -r src -ll` reports no medium/high findings.
- Architectural contract: `core` does not import `flagship` (enforced by
  `import-linter`).
