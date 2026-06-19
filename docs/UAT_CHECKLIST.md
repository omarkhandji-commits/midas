# MIDAS — Human UAT checklist

This list is what the operator (a human) signs off before claiming MIDAS works
end-to-end on a given machine. It is **not** replaced by the automated CI gates.
Sign each line by editing the file (`- [x]`) and committing.

Three OS columns. Treat unchecked = unknown, not "broken".

## Environment

| Item | Value |
|---|---|
| OS / version | _fill in_ |
| Python version | `python --version` |
| Node version (for /web) | `node --version` |
| Date of run (YYYY-MM-DD) | _fill in_ |
| Tester | _fill in_ |

## 1. Install from clean checkout

- [ ] **Windows** — Double-click `Launch MIDAS.bat`. Browser opens, dashboard reachable.
- [ ] **macOS** — Double-click `Launch MIDAS.command`. Browser opens, dashboard reachable.
- [ ] **Linux** — `./launch-midas.sh`. Browser opens, dashboard reachable.

Acceptance: rescue login link is printed if browser fails to auto-open.

## 2. Login + onboarding wizard

- [ ] Magic-link / one-time token authenticates on first try.
- [ ] `/start` wizard renders 4 steps without console error.
- [ ] Persona picker shows ≥ 3 options.
- [ ] After finishing the wizard, `/` (Chat) renders with sidebar visible.

## 3. Create + approve a mission

- [ ] Send a message in `/` Chat that triggers an `APPROVAL_REQUIRED` plan card.
- [ ] Card appears in `/approvals` with: action tier badge, payload JSON, cost estimate, expires-at, status `pending`.
- [ ] Click **Approve** → status flips to `approved`, **Execute** button appears.
- [ ] Click **Execute** → step runs, an `ALLOW` receipt appears in `/proofs`.

Acceptance: the receipt in `/proofs` shows the same `sha256_intent` as the
approval card. No console error.

## 4. Receipt verifier

- [ ] `pip install ./tools/verify`
- [ ] `midas keys export-public` prints a hex string.
- [ ] `python -m midas_verify .midas/receipts.jsonl --public-key <hex>` reports OK.
- [ ] Edit one byte in `.midas/receipts.jsonl` → verifier reports a corrupted sequence index.

## 5. Drift refusal (security)

- [ ] Approve a plan, then tamper with the payload between approval and execute
      (DB edit or replay a stale approval id). Execution refuses with `DENY` receipt.

## 6. Kill switch

- [ ] Set `MIDAS_KILL_SWITCH=on` in env → next agent step refuses with `DENY`.
- [ ] Unset → agent resumes normally.

## 7. Budget cap

- [ ] Lower per-task cap below the next planned step's projected cost.
- [ ] Agent step refuses with a budget-fuse DENY.

## 8. Egress untrusted defense

- [ ] In a single run, fetch an external URL (UNTRUSTED) then try a private
      file read + outbound `email.send`.
- [ ] Sentinel fires lethal-trifecta DENY before the send.

## 9. Persistence sanity

- [ ] Stop dashboard, restart, login again — pending approvals + receipts survive.
- [ ] `.midas/receipts.jsonl` is append-only on disk.

## Sign-off

Operator signature and date once all sections above are ticked:

```
Tester: _________________
Date:   YYYY-MM-DD
OS:     _________________
```
