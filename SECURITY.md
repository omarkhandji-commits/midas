# Security Policy

## Supported Versions

The project is pre-1.0. Only the latest published commit on `main` receives
security fixes.

## Reporting a Vulnerability

Do not open public issues for vulnerabilities. Use one of:

1. **GitHub Security Advisories** — preferred. Open a private advisory on this
   repository.
2. **Email** — the address listed on the maintainer's GitHub profile.

Please include:

- affected commit hash or release tag;
- minimal reproduction steps;
- expected vs. observed behaviour;
- impact assessment (secrets, PII, money movement, file writes, network
  egress);
- proof-of-concept if available.

Initial acknowledgement within 7 days. Coordinated disclosure is appreciated.

## Security Model

The full threat model is in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
Summary of defaults:

- **Approval-first execution.** All mutating tools (file writes, code
  execution, spreadsheet writes, outbound sends, external MCP calls) require
  human approval before the underlying callable runs.
- **Single chokepoint.** Every tool call passes through `Toolset.invoke()`,
  which evaluates the call against the policy gate and writes a receipt.
- **Signed receipts.** Each receipt is Ed25519-signed and links to the
  previous receipt's hash. Tampering one byte breaks verification.
- **Standalone verifier.** `tools/verify/midas_verify` re-checks a ledger
  using only PyNaCl and the standard library, with no imports from the main
  package.
- **Lethal-trifecta rule.** Steps combining untrusted input, private data
  access, and external egress are denied before the call body runs.
- **Budget fuse.** Per-task, daily, and monthly spend caps are enforced
  atomically before any LLM call.
- **Filesystem chokepoint.** All file paths resolve through `FsGuard`, which
  refuses `..` escapes, denied paths, and symlinks whose target leaves the
  workspace.
- **Workspace-confined code execution.** `code.run` executes in a subprocess
  with isolated interpreter, scrubbed environment, network monkey-patching,
  and wall-clock timeout. When a container runtime is available the execution
  is wrapped in a rootless container with `--net=none` and dropped
  capabilities; the isolation tier is recorded in the receipt.
- **Local-first surfaces.** The dashboard binds to loopback only and requires
  a one-time login token.

## Out of Scope

- Resource exhaustion on the host (operator-controlled).
- Vulnerabilities in third-party MCP servers connected by the operator —
  responses from such servers are tagged as untrusted, but the servers
  themselves are not maintained here.
- Supply-chain compromise of the operator's Python environment.

## No Compliance Claims

This project is not certified under any security, privacy, legal, or
regulatory framework. Independent assessment is recommended before any
production deployment that handles regulated data.
