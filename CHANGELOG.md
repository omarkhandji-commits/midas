# Changelog

## Unreleased

### Added — gated executor

- AgentLoop: bounded plan-execute loop driving every step through `Toolset.invoke()`,
  Sentinel verdict, signed receipt. CLI: `midas do "<task>"`.
- Artifact factory: `email.draft`, `pdf.draft`, `invoice.draft`, `voice.draft`,
  `code.draft`, `sheet.read`/`sheet.write`, `artifact.text` fallback. Every mutating
  artifact is APPROVE-tier; bytes live in the approval payload with sha256 of the
  proposed contents. CLI: `midas execute <approval_id>`, `midas fill <xlsx> --from <pdf>`.
- Filesystem chokepoint (`FsGuard`): workspace-only, `..` escape rejection, symlink
  target check, policy-driven deny list. Adversarial tests under `tests/security/`.
- Code sandbox (`code.run`): subprocess with isolated interpreter (`-I -S`), scrubbed
  env, poisoned proxy vars, network monkey-patch, wall-clock timeout, output cap. The
  callable never runs from `Toolset.invoke()` — only from `execute_code_approved()`
  after a human resolves the approval.
- `research.run` agent tool composing `SearchAdapter` + `Fetcher` + `SourceVerifier`
  with the Proof-First contract (no HIGH without verified sources).

### Added — proof + débrouillardise

- Receipt v1 specification (`docs/RECEIPT_V1.md`) with deterministic test vectors and
  a standalone verifier (`tools/verify/midas_verify`, PyNaCl + stdlib only, zero
  `midas.*` imports). CLI: `midas keys export-public`.
- Auto-skills (`flagship/autoskills.py`): proposals derived from completed 3-step
  receipt sequences; local-only sequences may auto-accept, anything network-touching
  goes through the approval queue. Multi-source tool discovery across PyPI, npm,
  crates.io, GitHub, MCP registry — not GitHub-only. CLI: `midas skills auto-list`,
  `auto-accept`, `auto-discard`.
- Débrouillard web research module (`core/web/research.py`) and `midas research`
  CLI. Proof contract: ≥3 verified sources → HIGH, 1–2 → MEDIUM, 0 → LOW.
- τ-bench rule-adherence adapter wired into the eval suite. `midas eval --suite tau`
  isolates the τ-bench cases.

### Added — surfaces

- Dashboard endpoints: `/api/research`, `/api/autoskills`, `/api/autoskills/{id}/accept`,
  `/api/autoskills/{id}/discard`, `/api/import`, enriched `/api/runs` with status.
- SPA pages for Memory, Market Radar, Outcomes, Schedule, Skills, Settings/Backup.

### Eval surface

- 33/33 deterministic cases across 11 evals, including:
  - Gated executor — no mutation without approval (E1)
  - Débrouillard artifacts — never refuse, always gated (E2)
  - τ-bench rule adherence with rule-adherence subscore (B)
  - Débrouillard web research — no HIGH without verified sources (D2)

### Tooling

- `[verify]` and `[sheets]` optional extras in `pyproject.toml`.
- PyPI distribution name `midas-agent` (`midas` is taken); CLI remains `midas`.
