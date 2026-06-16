# midas

[![CI](https://img.shields.io/badge/CI-passing-success)](.github/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-413%20passing-success)](#testing)
[![Type-checked](https://img.shields.io/badge/typed-mypy-blue)](pyproject.toml)

A local-first agent that prepares business work — landing pages, outreach
sequences, proposals, invoices, spreadsheets, code — and writes a signed,
hash-chained receipt for every step. Mutating actions queue an approval before
they touch the disk, the network, or your money.

```bash
pip install -e ".[llm,web]" && midas init
```

`midas init` detects a local model (Ollama) automatically, or takes one API
key and configures everything:

```bash
midas init                      # uses a running Ollama, no key needed
midas init --key sk-...         # OpenAI
midas init --key sk-ant-...     # Anthropic
midas init --key sk-or-...      # OpenRouter
```

It writes config, initializes local state, and runs a one-token smoke test —
a green line means you can run `midas earn "<niche>"` right away.

## What it does

- Plans and drafts work through a bounded agent loop.
- Stores every step as an Ed25519-signed receipt; the ledger is a hash chain.
- Routes mutating tools (file writes, code execution, spreadsheet fills, email
  drafts, PDFs, invoices) through an approval queue. The caller never executes
  inline.
- Exposes the same tools over the Model Context Protocol so editors and other
  agents can call them while keeping the approval contract.
- Reads an Obsidian-style vault and ranks the next cash moves it sees, citing
  the source notes.
- Joins receipted cost with operator-recorded outcomes into an explicit ROI
  ledger. Cost comes from the chain; revenue only from outcomes you record.

## Install

```bash
git clone https://github.com/<owner>/midas.git
cd midas
python -m venv .venv
.venv/bin/pip install -e ".[llm,web]"   # Windows: .venv\Scripts\pip
midas init
```

Optional extras: `dev` (test/lint tooling), `sheets` (xlsx writes), `docs`
(docx drafts), `verify` (standalone receipt verifier as a separate package).

## Usage

```bash
midas earn "<niche>"               # one cycle: scan, prepare, queue
midas pipeline                     # show every move's stage
midas approvals list               # see pending approvals
midas approvals approve <id>       # authorize one
midas execute <id>                 # materialize the approved action
midas roi                          # cost from receipts, revenue from outcomes
midas outcome record <run_id> "<note>" -m revenue=<amount>
midas proof export out.html --run-id <run_id>
```

Read a vault and rank the next moves:

```bash
midas advise /path/to/vault --live --start
```

Run as a Model Context Protocol server (for editors/clients that speak MCP):

```bash
midas mcp serve
```

Connect to an external MCP server:

```bash
midas mcp add filesystem npx -a -y -a @modelcontextprotocol/server-filesystem -a .
midas mcp test filesystem
```

## Verify a receipt chain

The verifier is a separate package with no project imports.

```bash
pip install ./tools/verify
midas keys export-public                          # print the public key (hex)
python -m midas_verify .midas/receipts.jsonl --public-key <hex>
```

Flip one byte in the ledger and rerun — the verifier reports the corrupted
sequence index.

## Configuration

`config/providers.example.yml` is seeded by `midas setup` as
`config/providers.yml`. Local providers (Ollama, LM Studio, vLLM, any
OpenAI-compatible endpoint) work without API keys. Cloud providers read keys
from the environment or the OS keychain.

`config/policy.yml` lists actions in three buckets:

- `allowed_without_approval` — reads, drafts, research, memory updates.
- `requires_approval` — file writes, code execution, spreadsheet writes,
  outbound sends, external MCP calls.
- `never` — spam, deception, unauthorized money movement, leaking secrets.

The local dashboard binds to `127.0.0.1:8765` and requires a one-time login
token printed at startup.

## Project layout

```
src/midas/core/        sentinel, budget fuse, receipts, memory, router
src/midas/flagship/    CLI, dashboard, agent loop, tools, eval suites, MCP
config/                policy + provider templates
docs/                  architecture, threat model, receipt spec
tests/                 unit, security, eval, fixtures
tools/verify/          standalone receipt verifier (no project imports)
```

## Testing

```bash
ruff check .
mypy src
lint-imports
bandit -r src -ll
pytest
midas eval
```

The eval suite is deterministic and ships test vectors for the receipt spec.
A live lane against a local model is available with `midas eval --suite live`.

## Security

See [SECURITY.md](SECURITY.md) for the reporting process and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)
for the detailed model. No certifications, no compliance claims.

## License

MIT — see [LICENSE](LICENSE).
