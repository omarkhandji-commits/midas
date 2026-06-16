---
name: Bug report
about: Report a reproducible defect.
title: "bug: "
labels: ["bug"]
---

### Description

A clear and concise description of the problem.

### Reproduction

```bash
# Exact commands run, including arguments.
```

### Expected

What you expected to happen.

### Actual

What actually happened. Include the full error message or relevant log lines.

### Environment

| | |
|---|---|
| OS | (e.g. Windows 11, macOS 14.5, Ubuntu 24.04) |
| Python | (`python --version`) |
| Commit | (`git rev-parse --short HEAD`) |
| Install command | (e.g. `pip install -e ".[llm,web,dev]"`) |

### Security impact

Tick any that apply.

- [ ] Secrets, credentials, or PII could be exposed
- [ ] Files outside the workspace could be written
- [ ] Network calls bypass the approval queue
- [ ] Receipt chain verification breaks

If yes to any: please report privately per [SECURITY.md](../../SECURITY.md)
instead of opening this issue.
