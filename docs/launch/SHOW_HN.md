# Show HN Draft

Do not post until the repository is public and the install flow has been tested
from a clean checkout.

## Title

Show HN: MIDAS, a local-first AI agent with approvals and signed receipts

## Body

I built MIDAS for people who want to try LLM automation without giving an agent
silent access to files, tools, or external services.

MIDAS runs from a local dashboard or CLI. It supports Ollama for local models,
cloud providers with user-supplied keys, MCP-oriented tool workflows, and an
approval queue for actions that change files, call services, publish content, or
use external tools.

The parts I would like feedback on:

1. Install flow for non-developers.
2. Approval model and risk labels.
3. Signed receipt format and independent verifier.
4. Local dashboard and CLI ergonomics.

Repo: https://github.com/omarkhandji-commits/midas
Receipt spec: https://github.com/omarkhandji-commits/midas/blob/main/docs/RECEIPT_V1.md
Verifier: https://github.com/omarkhandji-commits/midas/tree/main/tools/verify

Honest notes: MIDAS is pre-1.0. Cloud providers require your own API keys. Local
media workflows depend on tools installed on your machine. Read the disclaimer
before connecting external accounts or automation.

## Posting Notes

- Post only after the first public push and clean install test.
- Have one dashboard screenshot ready for the first comment.
- Do not post claims about results, rankings, or outcomes.
