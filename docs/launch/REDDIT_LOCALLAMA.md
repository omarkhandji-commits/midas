# r/LocalLLaMA Draft

Do not post until the repository is public and the Ollama path has been tested
from a clean checkout.

## Title

MIDAS: self-hosted LLM agent with Ollama support, approvals, and signed receipts

## Body

I released MIDAS, a local-first AI agent for LLM workflows that need review before
action. It can run with Ollama, or with cloud providers when you add your own API
key.

What may be useful to this community:

- Local dashboard and CLI.
- Ollama-first setup path.
- Approval queue for actions that change files, call services, publish content,
  or use external tools.
- Signed receipt ledger with an independent verifier.
- Budget controls before model calls.
- MCP-oriented tool workflow support.

Repo: https://github.com/omarkhandji-commits/midas

I would value feedback on the install flow, local model setup, approval model,
and receipt format.

Honest notes: MIDAS is pre-1.0. Local media workflows need local tools such as
Node, ffmpeg, or Remotion. External accounts and cloud providers stay opt-in.

## Posting Notes

- Post after the README badges render.
- Add the Ollama setup command in the first comment.
- Do not cross-post the same day.
