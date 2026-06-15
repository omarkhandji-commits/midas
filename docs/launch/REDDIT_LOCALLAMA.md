# r/LocalLLaMA post draft — MIDAS

**Title:** `MIDAS — open-source business agent that runs fully on Ollama, with hash-chained signed receipts you can verify with 100 lines of Python`

**Body:**

I've been bothered by how every "autonomous agent" project burns money on the
loudest cloud model and ships zero audit trail. So I built MIDAS — a local-first
business operator for founders / consultants / agencies.

What I think this sub will care about:

- **Runs fully on Ollama.** No vendor lock, no API keys required. Provider-agnostic
  router; if you have llama3.1 or qwen2.5 running on `127.0.0.1:11434`, you have
  a working agent. Cloud providers are opt-in, never the default.
- **Zero telemetry, zero CDN.** Dashboard is loopback-only with a strict CSP. The
  Python wheel ships every static asset; nothing phones home.
- **Every tool call writes a signed, hash-chained receipt.** Public spec at
  `docs/RECEIPT_V1.md`, with deterministic test vectors. A 100-line standalone
  verifier (`pip install pynacl`) reads your ledger and tells you OK or `bad_seq=N`.
- **Approval-default**, not a setting. Outbound actions enter an `ApprovalQueue` and
  a human resolves them from the dashboard, Telegram, Slack, Discord, etc. No
  full-auto bypass.
- **Budget fuse fires BEFORE the model call.** You can't blow past your cap on a
  runaway loop, even with a hosted endpoint.

Stack: Python 3.11+, FastAPI, Pydantic, PyNaCl for Ed25519, SQLite WAL, React + Vite
+ Tailwind for the SPA (built to static, no runtime CDN).

I'd love feedback on:
1. The eval suite (`midas eval` — 9 Proof-First invariants, deterministic, offline).
2. Receipt v1 — is the canonicalization rule sound? Test vectors are in the spec.
3. Whether the τ-bench-style rule-adherence subscore I added captures what people
   here would actually want measured.

Repo: https://github.com/<owner>/<repo>

Not "secure" or "certified" — those are organizational claims. The code does what
it does; the spec is public; the receipts verify.

---

**Posting notes:**
- Post on a Saturday morning ET (peak local-LLM crowd).
- Don't crosspost to r/MachineLearning the same day.
- First top-level comment should drop the Ollama config one-liner.
