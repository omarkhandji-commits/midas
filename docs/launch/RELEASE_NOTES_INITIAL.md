# Initial Release Notes Draft

Do not create a tag or GitHub release until this text is reviewed.

## What MIDAS Does

MIDAS is a self-hosted AI agent for LLM workflows that need review before action.
It includes a local dashboard, CLI, approval queue, signed receipts, budget
controls, Ollama support, cloud-provider setup, MCP-oriented tooling, and proof
export.

## Why It Exists

Many agent workflows are hard to inspect after they run. MIDAS keeps risky
actions behind approvals and records important steps in a receipt ledger so the
operator can review what happened.

## How To Try It

Windows:

```text
Double-click: Launch MIDAS.bat
```

macOS:

```text
Double-click: Launch MIDAS.command
```

Linux:

```bash
chmod +x launch-midas.sh
./launch-midas.sh
```

Developers can also run:

```bash
git clone https://github.com/omarkhandji-commits/midas.git
cd midas
python -m venv .venv
.venv\Scripts\pip install -e ".[llm,web,dev]"
midas init
midas dashboard
```

## Included

- Python CLI.
- Local FastAPI dashboard with React assets.
- Approval queue and approval center.
- Ed25519-signed receipt ledger.
- Budget controls.
- Capability scan and capability plan.
- Ollama and cloud provider setup.
- MCP-oriented workflow support.
- Media planning and Remotion project draft tools.
- Receipt verifier.

## Known Limits

- The project is pre-1.0 and APIs may change.
- GitHub metadata, topics, and social preview must be set in GitHub after push.
- Cloud providers require user-supplied API keys.
- Local media workflows depend on installed tools such as Node, ffmpeg, or
  Remotion.
- MIDAS is not professional advice and does not guarantee any result. Read
  [DISCLAIMER.md](../../DISCLAIMER.md).

## Next Steps

- Verify clean install from the public repo.
- Add real screenshots or a short demo video.
- Review first public issues and installation friction.
- Create the first GitHub release only after final approval.
