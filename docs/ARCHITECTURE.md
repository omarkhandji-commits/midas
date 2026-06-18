# Architecture

MIDAS is a local-first agent runtime with four public surfaces:

- Python CLI for developers and automation.
- Local FastAPI dashboard for non-terminal use.
- Approval queue for risky actions.
- Receipt ledger for review and verification.

The system is designed around one rule: analysis can run freely, but actions that
change files, call external services, publish content, or use connected tools must
pass through policy and approval.

## Runtime Flow

1. The user starts from the dashboard or CLI.
2. MIDAS loads settings, provider config, policy, skills, memory, and budget
   state.
3. The agent loop plans the next step.
4. Tool calls pass through Sentinel policy, taint checks, and budget checks.
5. Safe read-only work can run directly.
6. Risky work enters the approval queue with preview, risk, cost, expiry, and
   intent hashes.
7. Approved work runs only if the current payload still matches the approved
   intent.
8. Important steps write signed receipts.

## Core Modules

| Area | Responsibility |
|---|---|
| `midas.core.approvals` | Queue, approval records, approval metadata, gated execution |
| `midas.core.budget` | Per-task, daily, monthly, skill, and persona budget checks |
| `midas.core.receipts` | Signed receipt ledger and hash chain |
| `midas.core.sentinel` | Policy decisions and risk classification |
| `midas.flagship.agent` | Agent loop, tools, registry, and execution |
| `midas.flagship.dashboard` | Local web dashboard and APIs |
| `web/` | React dashboard frontend |
| `tools/verify/` | Standalone receipt verifier |

## Tool Model

Tools expose capability through the agent registry. The important distinction is
not whether a tool is powerful, but whether it is safe to run without review.

Examples that require approval:

- writing or overwriting files;
- running generated code;
- sending email or messages;
- publishing content;
- creating payment or subscription intents;
- installing or importing remote skills;
- using external services through MCP.

Examples that can usually run without approval:

- reading files inside the workspace;
- building a repo map;
- planning a draft;
- scanning local capabilities;
- producing a non-mutating preview.

## Taint Model

Fetched pages, PDFs, emails, MCP output, and third-party tool output are treated
as untrusted data. The agent may summarize or cite them, but it must not treat
instructions inside that content as operator instructions.

## Provider Model

MIDAS can use local Ollama or cloud providers configured by the operator. Provider
keys stay local and should be stored through the supported config path. The
dashboard and CLI expose setup flows, but external model calls remain the
operator's choice.

## Skills

Skills are indexed with lightweight metadata. MIDAS loads the full `SKILL.md`
only when the selected task needs that skill. Remote skills must be queued for
approval and review before they are installed.

## Dashboard

The dashboard runs on loopback and uses a one-time login token. It is intended to
make setup, chat, approvals, proofs, provider settings, channels, routines, and
capability checks usable without requiring terminal knowledge.

## Verification

Receipts use Ed25519 signatures and a hash chain. The standalone verifier in
`tools/verify/` can check a receipt ledger without importing the MIDAS runtime.

## More Detail

- Security model: [docs/SECURITY.md](SECURITY.md)
- Threat model: [docs/THREAT_MODEL.md](THREAT_MODEL.md)
- Receipt spec: [docs/RECEIPT_V1.md](RECEIPT_V1.md)
- Public setup: [docs/INSTALL_FOR_EVERYONE.md](INSTALL_FOR_EVERYONE.md)
