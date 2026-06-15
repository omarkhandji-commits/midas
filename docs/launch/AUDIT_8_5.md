# Pre-launch 8.5 audit checklist

This is the gate to flip the repo public. Every box must be checked before the
Show HN / r/LocalLLaMA / Twitter posts go out.

## Quality battery (run on a clean clone)

- [ ] `ruff check .` → All checks passed.
- [ ] `mypy src` → Success: no issues.
- [ ] `lint-imports` → `core must not depend on flagship KEPT`.
- [ ] `bandit -r src -ll` → Medium 0 / High 0.
- [ ] `pytest -q` → 256+ passed, 0 failed, 0 errors.
- [ ] `midas eval` → **PASS — N/N cases across 9 evals.**
- [ ] `python -m build` + `twine check dist/*` → both PASSED.
- [ ] `npm --prefix web run build` → SPA hashed assets land in
  `src/midas/flagship/dashboard/static/app/`.
- [ ] `npm --prefix web test` → vitest green.

## Spec + verifier (Sprint A)

- [ ] `docs/RECEIPT_V1.md` published with frozen v1 schema + test vectors.
- [ ] `tools/verify/midas_verify/` standalone package builds (`pip install .`).
- [ ] On a SEPARATE machine with only `pip install pynacl`,
  `python -m midas_verify tests/fixtures/receipts_v1_vector.jsonl --public-key 3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29`
  prints **"OK — 3 receipt(s) verified."**.
- [ ] Tamper any byte in the fixture → verifier returns non-zero with `bad_seq=0`.
- [ ] README badge `Receipt v1 — verifiable` renders correctly on GitHub.

## Demo videos (Sprint B.2)

- [ ] `docs/demos/01_verifiable_execution.md` recorded (≤90 s) — `01.mp4` in repo or release attachment.
- [ ] `docs/demos/02_approval_default.md` recorded (≤90 s).
- [ ] `docs/demos/03_local_first.md` recorded (≤90 s) with the wireshark frame.
- [ ] Each video published as an unlisted YouTube link or attached to the GitHub
  release; URLs added to README + launch posts.

## Launch kit (Sprint B.3)

- [ ] `docs/launch/SHOW_HN.md` — `<owner>/<repo>` placeholder replaced.
- [ ] `docs/launch/REDDIT_LOCALLAMA.md` — same.
- [ ] `docs/launch/TWITTER.md` — handles + links resolved.
- [ ] `TRANSPARENCY.md` updated with the latest τ-bench numbers (Pass@1 + adherence).
- [ ] `docs/COMPARISON.md` table still aligned with the positioning ("specialist
  business operator", not generalist).
- [ ] `docs/ROADMAP.md` reflects Streams V1 / D1 / D2 / A / B as completed.

## PyPI / GitHub (user-side)

- [ ] PyPI name `midas-agent` locked in `pyproject.toml` (DONE).
- [ ] Backup name `midas-operator` also reserved (user registers manually).
- [ ] First push to GitHub on `main` (user creates repo, sets remote).
- [ ] Live CI badge URL in README points at real `<owner>/<repo>`.
- [ ] GitHub About: short description + topics (`ai-agent`,
  `autonomous-agent`, `business-operator`, `local-first`, `proof-first`,
  `verifiable-execution`, `approval-default`) + social-preview image.
- [ ] `LICENSE` (MIT) shows correctly on GitHub.

## Marketing language compliance

- [ ] No occurrence of "secure / guaranteed / certified / compliant" as positive
  claims anywhere in README, COMPARISON, ROADMAP, TRANSPARENCY, launch drafts.
- [ ] DISCLAIMER.md surfaces the alpha + non-investment-advice clauses.
- [ ] `docs/SECURITY.md` THREAT_MODEL.md current; CSP concession (style-src
  unsafe-inline) is documented and justified.

## Known follow-ups (non-blocking for 8.5)

- SPA UI sections for auto-skills ("Auto-generated" block in `web/src/pages/Skills.tsx`)
  and a `Research` action in `Chat.tsx` / `Missions.tsx`. The backend endpoints
  (`/api/research`, `/api/autoskills`, `/api/autoskills/{id}/accept|discard`) are
  shipped + tested; the CLI surfaces (`midas research`, `midas skills auto-*`) work
  today. Adding the SPA panels requires `npm run build` + browser verification —
  schedule for V1.1 polish.

## Out of scope for THIS launch

- Posting Show HN / Reddit / Twitter — user posts when ready.
- First-100-stars / front-page outcomes — world-action, not ours.
- Receipt v2 — frozen at v1; breaking changes ship later.

## Sign-off

When every box is checked, MIDAS is at the 8.5 publishable state and the launch
sequence is the user's call.
