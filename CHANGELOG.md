# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
