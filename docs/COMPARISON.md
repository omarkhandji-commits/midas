# Comparison

MIDAS is not trying to replace every agent workspace. It is focused on one category:
**proof-first business operation**. It does the work AND proves it.

| Tool | Strong at | MIDAS difference |
|---|---|---|
| Hermes / Odysseus / OpenClaw | flexible general agents that "do anything" | every mutating step is approval-gated and writes a signed receipt — same débrouillardise, with audit |
| Claude Code / coding agents | editing repos, coding workflows | adds business memory, market radar, assets, gated executor for non-code artifacts |
| AutoGPT-style agents | autonomous task loops | hard budget fuse, cite-or-abstain, approval-default, no auto-execute toggle |
| Closed business AI tools | polished SaaS workflows | local-first, provider-agnostic, replayable transparency report + standalone verifier |
| Generic assistants | flexible reasoning | structured business runtime, receipts, gated artifact factory, outcomes loop |

**The 20× claim, honestly stated:** MIDAS is not 20× better at *being a general agent*.
It is 20× more trustworthy when the work crosses into business territory — money,
client deliverables, irreversible actions, anything you'd want a receipt for. The
operator gets Hermes-style débrouillardise (auto-skills, multi-source tool discovery,
web research with verified sources) wrapped in approval-default and signed receipts.

MIDAS should be judged by reproducible demos:

1. **do** something concrete — `midas do "draft an invoice for Acme, 10h consulting at $150"`
   produces a signed-receipted approval card with an actual PDF waiting for one tap;
2. **prove** it — every step (research, draft, write) is a hash-chained, Ed25519-signed
   receipt; tamper one byte and the standalone `midas-verify` returns FAIL at the
   corrupted `seq`;
3. **scale** the débrouillardise — auto-skills propose reusable sequences from completed
   runs; multi-source tool discovery searches PyPI / npm / crates.io / GitHub / MCP
   when something is missing, with approval before any install;
4. **never block** — if no tool fits, MIDAS falls back to a Markdown best-effort
   artifact rather than refusing the request.
