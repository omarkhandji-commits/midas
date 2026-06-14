# MIDAS

<img src="docs/assets/midas-mark.svg" alt="MIDAS mark" width="96" />

[![License: MIT](https://img.shields.io/badge/License-MIT-success.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](docs/ROADMAP.md)
[![Lint: Ruff](https://img.shields.io/badge/lint-Ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![Types: mypy](https://img.shields.io/badge/types-mypy-2a6db2.svg)](https://mypy-lang.org/)
[![Proof: 17/17 evals](https://img.shields.io/badge/proof-17%2F17%20evals-2a4d3a.svg)](TRANSPARENCY.md)

<!-- After the first push to GitHub, add the live CI badge (replace <owner>/<repo>):
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
-->

Proof-first business operator for founders, agencies, consultants, and small teams.

MIDAS researches a market, checks sources, proposes a Daily Revenue Move, drafts the
business assets, asks for approval before anything risky, records receipts, tracks
outcomes, and gets cheaper over time through cache, memory, local models, and budget
guards.

No revenue guarantee. No spam. No black-box autonomy. MIDAS is built to be useful in
real business work while keeping the operator in control.

## What MIDAS Does

- Finds business opportunities with source receipts, not model vibes.
- Generates assets: offers, landing copy, outreach email, SEO brief, objections,
  proposal/invoice PDFs, call script, video script, and a 7-day action plan.
- Tracks competitors through Market Radar snapshots and dated diffs.
- Keeps memory for user, business, decisions, results, market, and errors.
- Supports local and cloud LLM routing through LiteLLM-style model ids.
- Runs multi-LLM council reviews for high-stakes questions.
- Creates user-installed schedule recipes for cron, Windows Task Scheduler, and
  GitHub Actions.
- Creates and installs local skills with static safety checks; remote skills require
  approval before download.
- Inspects local PDFs, images, audio, and video safely; audio/video can use transcript
  sidecars without external calls.
- Drafts voice notes and consent-first call plans; no real call is placed by default.
- Ships a local Operator Console for approvals, proofs, memory, assets, market radar,
  and budget visibility.

## Why It Is Different

Most agents optimize for activity. MIDAS optimizes for proof, decisions, and outcomes.

| Agent type | Common failure | MIDAS behavior |
|---|---|---|
| Generic chat agents | Good advice, weak follow-through | Daily Revenue Move + assets + outcome loop |
| Auto-loop agents | Token burn and unsafe actions | budget fuse + approvals + receipts |
| Closed SaaS agents | Hard to audit or self-host | local-first, open repo, replayable evals |
| Dev workspaces | Strong coding, weak business memory | business memory + market radar + revenue assets |

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[llm,web,dev]"
.venv\Scripts\midas setup
.venv\Scripts\midas scan "agence SEO locale"
.venv\Scripts\midas eval
```

Open the local console:

```bash
.venv\Scripts\midas dashboard
```

Package note: the PyPI distribution name is `midas-agent` because `midas` is already
taken. The CLI command remains `midas`. See [docs/NAMING.md](docs/NAMING.md).

Configure providers:

```bash
.venv\Scripts\midas providers list
.venv\Scripts\midas providers doctor
.venv\Scripts\midas providers add ollama --role cheap --model ollama/llama3.1
.venv\Scripts\midas providers test ollama/llama3.1
```

Use a multi-model council only when stakes justify the cost:

```bash
.venv\Scripts\midas council "Should I launch this offer now?"
```

Create a schedule recipe, then install it yourself if you want:

```bash
.venv\Scripts\midas schedule recipe "agence SEO locale" --at 09:00 --mode deep
```

Create a local skill:

```bash
.venv\Scripts\midas skills create "market-radar-pro" "Track competitors and summarize opportunities."
```

## LLM Support

MIDAS is provider-agnostic. The example config supports:

- local: Ollama, LM Studio, vLLM, any OpenAI-compatible endpoint;
- cloud: OpenAI, Anthropic, Google Gemini, Azure OpenAI, Vertex AI, AWS Bedrock,
  Mistral, Groq, Together, OpenRouter, DeepSeek, Cohere, Perplexity, xAI,
  Cerebras, Fireworks, Replicate, Hugging Face.

Secrets stay in the OS keychain, `.env`, or environment variables. The dashboard
Providers screen can store keys in the keychain and test readiness without echoing keys
back to the browser. `providers.yml` stores only provider metadata and model ids.

## Safety Model

Default mode is approval-first. MIDAS may read, reason, draft, and prepare. It must
ask before external sends, public posts, money/legal actions, phone calls, risky local
writes, or remote skill downloads.

Core controls:

- Sentinel risk gate.
- Approval queue.
- Hash-chained receipts.
- Budget fuse.
- Source verifier.
- Context compression that preserves proof originals.
- Local dashboard locked to loopback.
- Skill registry with executable-payload rejection.

See [docs/SECURITY.md](docs/SECURITY.md), [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
and [DISCLAIMER.md](DISCLAIMER.md).

## Proof

Run the public eval suite:

```bash
.venv\Scripts\midas eval
```

Current transparency report: **17/17 cases across 7 evals pass**.

Covered invariants include fake-source clamping, unsourced model claims, budget fuse,
indirect prompt-injection exfiltration, context compression fidelity, asset quality,
local provider support, council human escalation, schedule safety, and skill install
safety.

## Core Commands

```bash
midas setup
midas dashboard
midas scan "<niche>"
midas providers list|doctor|add|test|example
midas council "<question>"
midas competitors add|list|watch
midas approvals list|approve|reject
midas memory add|search|export
midas outcome record
midas assets generate
midas schedule add|list|recipe
midas skills create|list|install|plan-download
midas media inspect
midas voice draft|call-plan
midas eval
midas export
```

## Repository Map

```text
src/midas/core/       core safety, routing, budget, memory, receipts, web, context
src/midas/flagship/   product runtime, CLI, dashboard, market radar, assets, evals
config/               policy and provider examples
docs/                 architecture, security, roadmap, scoring, threat model
tests/                deterministic unit/security/API eval coverage
TRANSPARENCY.md       current reproducible eval report
```

## Launch Notes

MIDAS is not financial, legal, tax, security, or medical advice. It does not guarantee
income, leads, rankings, sales, or business results. Operators are responsible for
reviewing actions, following laws, respecting platform rules, and validating outputs.

License: MIT.
