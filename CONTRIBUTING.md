# Contributing

Thank you for considering a contribution.

## Development Setup

```bash
git clone https://github.com/omarkhandji-commits/midas.git
cd midas
python -m venv .venv
.venv/bin/pip install -e ".[llm,web,dev]"
.venv/bin/midas setup
```

On Windows, replace `.venv/bin/...` with `.venv\Scripts\...`.

## Required Checks

Before opening a pull request, run the full battery locally. The CI pipeline
enforces the same set.

```bash
ruff check .
mypy src
lint-imports
bandit -r src -ll
pytest
midas eval
```

A pull request is mergeable when all six pass.

## Code Conventions

- Target Python 3.11+. Use modern syntax (`X | None`, `match`, `tomllib`).
- Public APIs carry type hints and short docstrings.
- New mutating behaviour requires an approval test in `tests/security/` or
  `tests/unit/` proving the call queues an approval rather than running
  inline.
- New external integrations ship with a dry-run or mocked test path; live
  integration tests are opt-in and live behind `--suite live`.
- Do not import `midas.flagship.*` from `midas.core.*`. The constraint is
  enforced by `import-linter`.
- Do not log secrets or include them in fixtures, receipts, or test snapshots.

## Pull Request Checklist

- [ ] Tests cover the change.
- [ ] `ruff`, `mypy`, `lint-imports`, `bandit`, `pytest`, `midas eval` all
      pass locally.
- [ ] Public-facing strings (README, help text, error messages) avoid
      unsubstantiated claims.
- [ ] New risky behaviour has an approval-gating test.
- [ ] `CHANGELOG.md` is updated under `[Unreleased]`.

## Reporting Bugs

Use the issue templates in `.github/ISSUE_TEMPLATE/`. Include reproduction
steps and the output of `midas version` plus your platform.

## Security Reports

Do not open public issues for security findings. Follow [SECURITY.md](SECURITY.md).

## License

By submitting a contribution you agree to license it under the project's MIT
license.
