# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`blog.seo_lint` tool — WS-V foundation, deterministic SEO checklist.**
  AUTO-tier, pure text, no egress, zero install footprint (regex
  only). Parses optional YAML-ish front-matter (`title`, `description`)
  and runs the table-stakes checks: title length (30–60), meta
  description (70–160), single H1, no heading-level skips, ≥300-word
  body, every image carries alt text, at least one internal link.
  Returns a 0–100 score with per-issue severity. Honest: this is the
  documented Google Search Essentials checklist, NOT a ranking
  guarantee — we don't call SERP APIs, don't claim "this will rank".

- **`execute_code_edits` executor — Phase 6 step 3, closes the edit loop.**
  Post-approval handler wired into the execute pipeline. Re-runs
  `plan_code_edits` from the canonical `edits` list inside the
  payload; if the resulting `sha256_intent` doesn't match the approved
  one, the write is REFUSED (DENY receipt). On match, writes each
  modified file atomically and emits an ALLOW receipt with
  files_written + bytes_written.

- **`code.edit_plan` tool — Phase 6 step 2, exact-match multi-file edits.**
  APPROVE-tier (`repo_write`). Input is a list of
  `{file, old, new}` edits; per edit, `old` MUST appear exactly once in
  the file or the whole plan refuses (zero match → re-read; multi
  match → add more surrounding context to disambiguate). Multiple
  edits to the same file apply in declaration order so a later edit
  can reference text inserted by an earlier one. Output carries the
  sha256-of-intent and per-file LOC delta. All-or-nothing — if any
  single edit fails to validate, NO file is touched. Safety cap: 50
  edits per plan. Foundation of the Aider-diff format edit loop.

- **`code.repo_map` tool — Phase 6 step 1, foundation of the native coder.**
  AUTO-tier AST walk + import-graph ranking. Uses the stdlib ``ast``
  module — no tree-sitter native build, no third-party deps. Returns
  per-file top-level functions, classes, imports, plus an in-degree
  score (files imported by many others bubble up). The ``top`` field
  surfaces the most depended-on files for prompt-economical planning.
  Honest: in-degree ≠ true PageRank — it's the 90%-correct linear-time
  heuristic. Real PageRank iteration is a future slice. Python-only
  this slice; JS/TS/Go ranking is additive (the data shape is
  language-agnostic). NO benchmark claim — Aider Polyglot scoring
  needs the harness installed and the dataset, both follow-up work.

- **Adapter extensions — IG carousel, YouTube video upload, TikTok status poll.**
  Instagram adapter now publishes multi-image carousels (cap 10, per
  Graph API): one child container per URL, parent CAROUSEL container,
  publish. YouTube adapter now uploads videos via resumable upload
  (POST init → PUT bytes); title taken from first line of text (100
  char cap), description from full text, privacy from
  `YOUTUBE_PRIVACY` env (default `private` — operator flips after
  reviewing in YouTube Studio). TikTok adapter gains
  `fetch_status(publish_id, …)` polling /publish/status/fetch/ —
  returns `tiktok_ok` on `PUBLISH_COMPLETE`, raises on `FAILED` with
  the surfaced reason, returns `tiktok_pending_timeout` (empty
  permalink — never invents one) when poll budget runs out. Polling
  is opt-in via `TIKTOK_POLL=1`.

- **`drain_due()` + `POST /api/scheduled-posts/drain` — close the scheduling loop.**
  Drains pending posts whose `scheduled_at_iso` <= now by re-validating
  intent through `plan_social_publish` and enqueuing a `send_social`
  approval. Post transitions `pending → queued`. Honest: NO auto-egress —
  the operator still resolves the approval before any network call.
  A failed re-plan (e.g. media file deleted) marks the post `failed`
  with the validation reason; nothing reaches the queue.

- **Calendar page (`/calendar`).** 7-day grid view of `/api/scheduled-posts`.
  Monday-anchored, UTC, prev/this-week/next navigation, per-post status
  badge (pending/published/failed/cancelled), inline cancel button for
  pending posts. Honest: time displayed as UTC HH:MM — local conversion
  is left to V2 (timezone discovery requires either persona prefs or a
  browser-locale read, both worth a separate slice).

- **`ScheduledPostStore` + `/api/scheduled-posts` — queued social posts.**
  JSON-backed queue of pending posts with a `scheduled_at_iso`
  timestamp. ISO-8601 with explicit timezone is enforced (naive
  timestamps refused — local-vs-UTC ambiguity is the kind of bug
  that publishes at the wrong hour). Status is one-way:
  `pending → published | failed | cancelled`. Single-process lock for
  add/mark/cancel. Endpoints: GET `/api/scheduled-posts` (filter by
  status/start/end window), POST add, DELETE cancel — receipt-logged.
  Honest: we do NOT auto-fire — a separate drain step re-validates
  through `plan_social_publish` and queues normal approval. The
  store records intent only.

- **`lead.record` tool — CRM bridge inbox → memory.**
  AUTO-tier, no egress. Takes the `messages` list from
  `email.inbox.read` and promotes intent-shaped messages to
  `MemoryKind.RESULT` entries tagged `["lead", "cash-signal"]`. Dedup
  key `lead:{from_addr}:{uid}` makes re-runs idempotent. The intent
  classifier is a small fixed keyword list (`interested`, `demo`,
  `quote`, `pricing`, `buy`, `budget`, `invoice`, `proposal`, …) —
  conservative on purpose (false positives waste planner attention).
  Honest: we do NOT auto-reply, do NOT mark-as-read, do NOT write
  `MemoryKind.CASH` (no money has moved — `cash-signal` tag biases
  the planner without lying about proof level). `proof_level=LOW`,
  no sources. Cap 100 messages per call.

- **`affiliate.link.generate` tool — Phase 7 cash vein.**
  AUTO-tier pure URL builder: takes a merchant URL and a campaign,
  returns a tracked link with UTM params (`utm_source`, `utm_medium`,
  `utm_campaign`, optional `utm_content` / `utm_term`) plus a sha256
  the operator can reconcile against the merchant's affiliate
  dashboard. Honest: refuses to silently overwrite an existing UTM
  on the merchant URL (almost always a planner mistake); refuses
  non-http(s) schemes; refuses `extra_params` that collide with
  reserved UTM keys; URL is NOT cloaked (FTC / ASA / EU UCPD
  disclosure rules). Output `Taint.TRUSTED`, no egress.
- **3 new exhaustive security invariants (Phase 8 fortress).**
  (a) `email.send` REFUSES bulk (>1 recipient) without an unsubscribe
  affordance — CAN-SPAM / CASL / GDPR. (b) `stripe.payment_link.draft`
  refuses a `pk_*` publishable key at plan time. (c) `code.complex`
  SCRUBS provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `STRIPE_API_KEY`, …) from the subprocess env before invoking the
  `claude` CLI — sub-agent runs under its own auth.

- **`email.send` tool — APPROVE-tier SMTP send (STARTTLS / SSL).**
  Closes the outreach loop: ``email.draft`` writes the ``.eml``,
  ``email.send`` actually puts it on the wire. Plan validates
  recipients (RFC-2822 syntax), subject, body (50k cap), 100-recipient
  ceiling. Payload carries the canonical message + sha256_intent;
  executor refuses on drift. Honest constraints baked in: (1) bulk
  (>1 recipient) without an unsubscribe affordance is REFUSED at plan
  time — CAN-SPAM / CASL / GDPR all require it; (2) plaintext SMTP
  (port 25) is refused at execute time — STARTTLS (587) or SSL (465)
  only; (3) ``SMTP_HOST`` / ``SMTP_USER`` / ``SMTP_PASSWORD`` /
  ``SMTP_FROM`` read at execute time only. Action: ``send_email``
  (already APPROVE in default policy). Failed send writes DENY receipt.
- **`email.deliverability_check` tool — honest SPF/DKIM/DMARC posture.**
  AUTO-tier DNS-only check: queries the domain's TXT records, parses
  SPF (with ``-all`` / ``~all`` / redirect detection), probes DKIM at
  10 common selectors (override via ``dkim_selectors``), parses DMARC
  (policy + ``rua`` + ``pct``). Returns a heuristic 0–100 score and a
  concrete fix list. Honest: the score is a proxy, not a guarantee —
  real deliverability also depends on content, warmup, reputation; the
  receipt's ``proof_level=MEDIUM`` cites the actual DNS records, never
  fabricated. dnspython is an optional dep; missing it surfaces a clear
  install message.
- **`email.inbox.read` tool — surfaces inbound leads without state change.**
  AUTO-tier IMAP fetch that reads up to N recent (unread) messages and
  returns structured rows (from address + name, subject, snippet,
  date, has_attachment). Selects the folder with ``readonly=True`` —
  we do NOT mark messages as read on the server, move them, or delete.
  Credentials env-only (``IMAP_HOST`` + ``IMAP_USER`` +
  ``IMAP_PASSWORD``, optional ``IMAP_PORT``), read at call time only.
  Honest constraints: (1) refuses plaintext IMAP (port 143) — SSL only;
  (2) body snippet capped at 500 chars per message — full bodies are a
  read-the-message-later concern; (3) attachments not parsed; (4) does
  NOT classify a message as a "lead" — returns structured rows, the
  planner decides. Output ``Taint.UNTRUSTED``. New capabilities group
  ``Inbound`` to keep inbound surface separate from outbound drafts.
- **`web.automate` tool — APPROVE-tier interactive web automation.**
  Sibling to ``web.scrape``: where scrape is a read-only render,
  automate performs a small declared sequence of actions
  (``navigate``/``click``/``fill``/``wait``/``screenshot``). NO
  ``evaluate`` step — arbitrary JS would let the planner exfiltrate
  session data. Sequence capped at 20 actions. Action: ``execute_code``
  (APPROVE). Payload carries the canonical JSON + a sha256; executor
  refuses on drift. Honest constraints baked in: (1) ``fill`` selectors
  that look password-shaped (``password``, ``pwd``, ``secret``, ``pin``,
  ``otp``) are REFUSED at plan time — credentials belong in a vault, not
  in an approval payload; (2) robots.txt respected at navigate, override
  per-call; (3) per-host rate limit shared with ``web.scrape``;
  (4) captcha detection triggers a clean stop, never a bypass.
- **Persona presets (`GET /api/personas`).** Five opinionated starter
  profiles to make the new-user wizard concrete instead of overwhelming:
  Freelance developer, Independent consultant, Content creator,
  E-commerce / Etsy seller, Local business. Each carries a tagline, a
  ready-to-paste first action, a small set of recommended skills (from
  ``seed_skills/``), and the operator's default currency. Pure data
  module — no secrets, no egress.
- **Voice synthesis tool (`voice.synthesize`).** Provider-agnostic TTS,
  sibling pattern to ``image.draft``: planner generates audio bytes,
  stores base64 in the approval payload with sha256; executor writes
  through ``execute_fs_write`` after approval. Two backends ship:
  ``offline`` (deterministic stdlib WAV — short 440Hz tone + silence
  scaled by script length, always available, honest placeholder) and
  ``openai`` (opt-in, ``tts-1``, requires ``OPENAI_API_KEY``, validates
  voice name against the supported set up front). The plan refuses to
  mislabel format — if the backend produced ``.wav`` but the path says
  ``.mp3``, the receipt would lie, so we ``raise`` instead.
- **Sub-agent Claude Code (`code.complex`).** Delegates heavy / multi-file
  coding tasks to the operator's local ``claude`` CLI rather than
  reimplementing that engine. Plan validates prompt + workdir; payload
  carries the sha256 of the prompt. Executor shells out to ``claude -p
  "<prompt>" --output-format json`` in the approved workdir with a
  timeout (5-min default, 30-min ceiling) and parses the JSON result.
  Action: ``execute_code`` (already APPROVE-tier). Honest constraints:
  (1) MIDAS provider keys are stripped from the subprocess env — Claude
  Code uses its own auth, the two stay separate; (2) no fallback to
  ``code.run`` on failure (DENY receipt + raise — operator decides);
  (3) the subagent's output is ``Taint.UNTRUSTED`` and any filesystem
  changes still flow through MIDAS's ``fs.write`` approval.
- **YouTube + TikTok social adapters.** ``YouTubeAdapter`` posts to the
  Community tab via the YouTube Data API v3 (requires user OAuth token —
  NOT an API key — and ``YOUTUBE_CHANNEL_ID``); refuses video upload in
  this slice (resumable + multi-part flow ships next). ``TikTokAdapter``
  initializes a photo post via the Content Posting API v2 (``DIRECT_POST``,
  ``PULL_FROM_URL``); requires ``TIKTOK_ACCESS_TOKEN`` + ``TIKTOK_OPEN_ID``;
  refuses text-only (TikTok is media-first by API design) and local file
  paths (the platform pulls from a public URL). The asynchronous status
  poll ships in a follow-up — for now we return the ``publish_id`` so the
  receipt has a stable handle.
- **Facebook + Threads social adapters.** ``FacebookAdapter`` posts text
  updates to a Page feed via Meta Graph (``FACEBOOK_PAGE_TOKEN`` +
  ``FACEBOOK_PAGE_ID``; personal profiles are no longer supported by Meta's
  API so we refuse early). ``ThreadsAdapter`` posts text via the Meta
  Threads API's two-step container+publish flow (``THREADS_ACCESS_TOKEN`` +
  ``THREADS_USER_ID``), with 500-char limit. Media attachments queued for
  the next slice; both refuse media calls with a clean message rather than
  silent degrade.
- **Reddit social adapter (`RedditAdapter`).** Posts self-text submissions
  via Reddit's API ``/api/submit``. Requires a script-type OAuth app and
  four env vars: ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``,
  ``REDDIT_USERNAME``, ``REDDIT_PASSWORD``. The post's title is the first
  line of ``text``, the body is everything after. Honest constraint:
  ``account_handle`` carries the target subreddit (``r/<sub>``) — Reddit is
  sub-scoped, not handle-scoped, and we don't pretend otherwise.
- **Instagram social adapter (`InstagramAdapter`).** Posts single images
  with caption via the Meta Graph API (two-step container + publish).
  Requires ``INSTAGRAM_ACCESS_TOKEN`` + ``INSTAGRAM_USER_ID`` (Business or
  Creator, not personal). Honest constraints surfaced as ``SocialAdapterError``
  rather than silent degrade: (1) text-only posts not supported by the
  Instagram API; (2) the API needs a public HTTPS URL for the image, not a
  local file path; (3) carousel (multi-image) ships next.
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
