# Demo 3 — Local-first, no cloud (≤90 s)

**One-line hook.** *Pull the ethernet cable. MIDAS keeps going. Local Ollama,
local dashboard, local receipts. Same Daily Revenue Move, same proofs.*

## Why this demo

The privacy-conscious cohort doesn't need to be convinced MIDAS is open-source —
they need to see it actually run with zero network. This demo proves it.

## Pre-roll setup

1. Ollama running locally with `llama3.1` (or any chat-capable open model) pulled.
2. `midas providers add ollama` — provider stored in keychain.
3. Memory pre-loaded with one niche the operator cares about.
4. **Disable Wi-Fi physically before recording.**

## Storyboard

| 0:00–0:08 | Title: **"Wi-Fi off. Everything else on."** Show the OS network indicator turning off. |
| 0:08–0:18 | Open dashboard at `http://127.0.0.1:8765`. Run a fresh `midas scan "fractional CFOs"`. |
| 0:18–0:40 | The agent works: research uses the cached fetcher + memory-grounded context (no SearXNG needed); LLM calls go to Ollama on `127.0.0.1:11434`. Budget meter ticks $0.00 — local model, no cost. |
| 0:40–0:55 | Daily Revenue Move appears with cited sources from the existing memory + cache. Proof Ledger shows fresh receipts being signed. |
| 0:55–1:10 | Cut to a packet capture (Wireshark) showing **zero outbound traffic** during the run. |
| 1:10–1:25 | Closing card: **"Your data stays on your machine. So do your receipts."** |

## Voice-over script

> The network is off. Watch what happens.
>
> The agent runs. The dashboard renders. The model — running on Ollama, on this
> laptop — answers. The receipts get signed by the local key. None of it leaves
> this machine.
>
> No vendor lock-in, no telemetry, no rate limits, no surprise cost spike.

## Captions

- `0:18` — *"`midas providers add ollama` — local model, no API key."*
- `0:40` — *"Spent: $0.00 — local inference, no cloud spend."*
- `0:55` — *"Wireshark: 0 outbound packets during the run."*

## Editor notes

- Show the Wi-Fi off indicator clearly at the start, then again at the end.
- The packet capture is the proof — keep it on screen long enough to read.
- Do not say MIDAS is "private" or "secure" — show the network is off and let
  the viewer draw the conclusion.
