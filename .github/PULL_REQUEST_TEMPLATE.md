### Summary

What changes, and why.

### Type

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] Feature (non-breaking change that adds capability)
- [ ] Breaking change (fix or feature that changes existing public behaviour)
- [ ] Refactor (no behaviour change)
- [ ] Docs / build / CI only

### Checks

- [ ] `ruff check .`
- [ ] `mypy src`
- [ ] `lint-imports`
- [ ] `bandit -r src -ll`
- [ ] `pytest`
- [ ] `midas eval`

### Security

- [ ] No new mutating action runs without an approval-gating test.
- [ ] No secrets, PII, or live API keys in tests, fixtures, or receipts.
- [ ] No new outbound automation without an explicit `requires_approval` action.

### Changelog

- [ ] `CHANGELOG.md` updated under `[Unreleased]`, or N/A.

### Linked issues

Closes #
