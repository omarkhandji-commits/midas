# Public Release Readiness Checklist

Use this checklist before making launch posts or creating a release.

## Required Local Gates

- [ ] `ruff check src tests`
- [ ] `mypy src --no-incremental --no-sqlite-cache`
- [ ] `lint-imports`
- [ ] `bandit -q -r src`
- [ ] `pytest`
- [ ] `midas eval`
- [ ] `npm run lint`
- [ ] `npm test`
- [ ] `npm run build`
- [ ] `python -m build`
- [ ] `twine check dist/*`
- [ ] secret scan
- [ ] placeholder scan
- [ ] old logo scan
- [ ] `git diff --check`
- [ ] ShipVitals deep review

## GitHub Setup

- [ ] Repository exists at `https://github.com/omarkhandji-commits/midas`.
- [ ] README clone URL points to the real repo.
- [ ] `GITHUB_SETUP.md` has the final description and topics.
- [ ] GitHub About description is set.
- [ ] GitHub topics are set.
- [ ] Social preview image is uploaded.
- [ ] CI and CodeQL badges render after first push.

## Public Files

- [ ] `DISCLAIMER.md` is visible from README.
- [ ] `docs/INSTALL_FOR_EVERYONE.md` explains the launcher path.
- [ ] `docs/SECURITY.md` and `docs/THREAT_MODEL.md` are current.
- [ ] `docs/launch/SHOW_HN.md` uses the real repo URL.
- [ ] `docs/launch/REDDIT_LOCALLAMA.md` uses the real repo URL.
- [ ] `docs/launch/TWITTER.md` uses the real repo URL.
- [ ] `docs/launch/RELEASE_NOTES_INITIAL.md` is ready for review.

## Language Rules

- [ ] No claim that MIDAS guarantees results.
- [ ] No claim that MIDAS is certified or compliant.
- [ ] No comparison against named agent projects in public launch copy.
- [ ] No placeholder owner or repo paths.
- [ ] No personal drafts or private replies.

## Manual Follow-Ups

- Take real dashboard screenshots after the public repo is live.
- Record a short demo only after the clean install path is confirmed.
- Create a GitHub release only after separate approval.
