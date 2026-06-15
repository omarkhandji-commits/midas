# Demo 1 — Verifiable execution (≤90 s)

**Hook.** *A 15-step research mission. One byte flipped in the ledger. A 100-line
standalone verifier catches it.*

## Premise

Other open-source agents do not ship a hash-chained, signed receipt ledger paired with
a verifier an auditor can run without trusting the agent runtime. Receipt v1 makes
that property concrete.

## Pre-roll setup (off-camera)

1. Fresh `pip install -e ".[llm,web,dev]"` checkout, `.venv` activated.
2. `midas setup` — produces `.midas/signing.key`, empty ledger.
3. A second venv on a **different** machine (or `python -m venv /tmp/auditor`) with
   only `pip install pynacl` and `tools/verify/` copied over.

## Storyboard (timing in seconds)

| 0:00–0:08 | Title card: **"Receipt v1 — proofs you can re-verify yourself."** |
| 0:08–0:25 | Run `midas research "best SEO playbook for local dentists 2026"` — wait for the cited markdown synthesis to print. |
| 0:25–0:35 | Show the resulting JSONL ledger (`.midas/receipts.jsonl`). Highlight: `seq`, `prev_hash`, `inputs_hash`, `outputs_hash`, `sig`. |
| 0:35–0:42 | On the agent machine: `midas keys export-public` → copy the hex public key. |
| 0:42–0:55 | Switch to the auditor machine. `python -m midas_verify .midas/receipts.jsonl --public-key <hex>` → **"OK — N receipt(s) verified."** Pause. |
| 0:55–1:08 | Back to agent. Open ledger in an editor. Flip **one byte**: change one `"allow"` to `"deny"` in seq 7. Save. |
| 1:08–1:22 | Re-run the verifier on the auditor machine. **"FAIL — hash mismatch at seq 7 (after 7 OK, bad_seq=7)."** Slow zoom on the line. |
| 1:22–1:30 | Closing card: `docs/RECEIPT_V1.md` — public spec + test vectors. |

## Voice-over script (60–75 spoken seconds)

> Most AI agents ask for trust. MIDAS hands over a verifier instead.
>
> Every action — every search, every fetch, every approval — gets a signed,
> hash-chained receipt. The test is what happens when one is tampered with.
>
> A fresh research run. Fifteen tool calls, fifteen receipts, all chained.
>
> Different machine — clean Python, only PyNaCl installed. Run the standalone
> verifier. Receipts verified.
>
> Now open the ledger. Change one byte. Save.
>
> Re-run the verifier. Caught. Sequence 7. Hash mismatch.
>
> No trust in the agent runtime required. That is verifiable execution.

## Captions / lower-thirds (display on screen)

- `0:25` — *"Hash chain: every receipt's `prev_hash` is the previous receipt's hash"*
- `0:55` — *"Public spec: `docs/RECEIPT_V1.md`"*
- `1:08` — *"Tamper: changed `\"allow\"` → `\"deny\"` at seq 7"*

## Assets needed

- Terminal recording (asciinema or simple screencap).
- Two visible terminal windows (agent + auditor) — split-screen at 0:42.
- Static title cards (`01_title.png`, `01_closing.png`) — sober, no animation.

## Notes for the editor

- **No music** with a beat. Light ambient pad at most. This is a credibility piece.
- **Never** use the words "secure", "guaranteed", "certified", "compliant".
- Keep B-roll out: every frame is the actual terminal.
