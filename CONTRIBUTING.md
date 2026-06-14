# Contributing

MIDAS values proof over hype. Contributions should improve usefulness, auditability,
safety, or operator experience.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[llm,web,dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\midas eval
```

## Rules

- Do not add outbound automation without approval gates.
- Do not add revenue guarantees or unverifiable benchmark claims.
- Do not put secrets in tests, docs, fixtures, or receipts.
- Keep deterministic tests for safety behavior.
- Prefer local-first adapters and mockable interfaces.
- Preserve proof originals when compressing context.

## Pull Request Checklist

- Tests pass.
- `midas eval` passes.
- Public docs do not overclaim.
- New risky behavior has an approval test.
- New external integrations have a dry-run or mock path.
