# Release Checklist

Run before publishing a release.

```bash
.venv\Scripts\python -m pytest -q -p no:cacheprovider
.venv\Scripts\midas eval
.venv\Scripts\ruff check src tests
.venv\Scripts\python -m build
```

Manual checks:

- README quickstart works from a clean checkout.
- Dashboard opens only on loopback.
- No secrets in `git diff`, docs, tests, or receipts.
- `TRANSPARENCY.md` matches `midas eval`.
- Disclaimer and security policy are visible from README.
- Example provider config includes local and cloud models.
- Remote skill download stays approval-gated.
- Schedule commands are recipes only, not silently installed.
- ShipVitals verdict is recorded before public launch.
