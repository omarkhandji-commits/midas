# Push to GitHub

The repository is committed on `main`, no remote configured. Follow these steps
from the project root to publish it.

> **Do not skip the secret check.** Run step 1 even if you trust the repository
> state — five seconds of prevention.

## 1. Secret check (mandatory)

```bash
git ls-files | xargs grep -lE "(api[_-]?key|secret|password|token|sk-[a-zA-Z0-9]{20,})" 2>/dev/null
```

Expected output: empty. If anything prints, inspect the file and either remove
the secret or add the path to `.gitignore` and run `git rm --cached <path>`
before pushing.

## 2. Create the repository on GitHub

Create a new repository under your account. **Do not** initialize it with a
README, `.gitignore`, or LICENSE — those already exist locally and would
conflict on the first push.

- Visibility: public.
- Default branch: `main`.
- Repository name suggestion: `midas-agent` (matches the PyPI distribution name
  declared in `pyproject.toml`). Any name works; the choice does not affect
  the package.

## 3. Wire the remote and push

Replace `<owner>` with your GitHub username or organization, and `<repo>` with
the repository name you chose in step 2.

```bash
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```

If the remote requires SSH, use `git@github.com:<owner>/<repo>.git` instead.

## 4. Fill the live CI badge

`README.md` line 13 contains a commented-out badge template. Replace
`<owner>/<repo>` with the real path and uncomment the line:

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
```

Commit and push the change. The badge turns green when the first workflow run
finishes.

## 5. Repository settings on GitHub

In the **About** panel of the repository home page:

- **Description**: `Proof-first business operator. Gated executor with signed, hash-chained receipts and a standalone verifier.`
- **Website**: leave blank until a project site exists.
- **Topics**: `ai-agent`, `autonomous-agent`, `business-operator`, `local-first`, `proof-first`, `verifiable-execution`, `approval-default`, `python`, `fastapi`.
- **Social preview**: upload `docs/assets/midas-mark.svg` (or a 1280×640 PNG
  derived from it) under Settings → General → Social preview.

Under **Settings → General**:

- Disable "Allow merge commits" if linear history is preferred. Keep "Allow
  squash merging" and "Allow rebase merging".
- Enable "Automatically delete head branches".

Under **Settings → Branches**:

- Protect `main` with: require pull request reviews (1), require status checks
  to pass (`ci` once the workflow has run once), require branches to be up to
  date before merging.

## 6. PyPI name reservation (optional, recommended)

The distribution name `midas-agent` is currently free on PyPI; so is
`midas-operator` as a backup. Reserve both with a 0.0.0 placeholder release if
you intend to ship to PyPI later:

```bash
.venv/Scripts/python -m build
.venv/Scripts/twine upload dist/*
```

`midas` itself is taken (Honeywell gas-detector driver) and cannot be used as
the distribution name.

## 7. After the first push: verify the quality battery in CI

The included GitHub Actions workflow runs ruff, mypy, import-linter, bandit,
pytest, `midas eval`, and a wheel build with `twine check`. On the first push,
visit the **Actions** tab and confirm the workflow finishes green. If it does
not, inspect the failing step; nothing in the code requires network access at
test time, so any failure is a configuration issue rather than a behavioral
regression.

## 8. Launch artifacts

Drafts ready under `docs/launch/` are intentionally not posted from this repo.
Publish them from your own accounts when ready:

- `docs/launch/SHOW_HN.md`
- `docs/launch/REDDIT_LOCALLAMA.md`
- `docs/launch/TWITTER.md`
- `docs/launch/AUDIT_8_5.md` — pre-launch checklist; mark items off before
  publishing.

Demo video scripts under `docs/demos/` describe three reproducible recordings.
Render them when convenient and link from the README.

---

The repository is otherwise ready. No further code changes are required to
push.
