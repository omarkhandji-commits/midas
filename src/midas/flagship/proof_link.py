"""Proof Links — self-contained, offline-verifiable proof of a run.

Exports the receipts for one ``run_id`` as a single HTML file embedding a pure-JS
verifier. A client opens it in any browser with **no installation**, no network,
no MIDAS dependency, and sees ``chain OK`` or ``FAIL at seq N``.

The verifier re-implements the four Receipt v1 chain rules from
``docs/RECEIPT_V1.md`` in JavaScript:

1. ``seq`` is monotonic from 0.
2. ``prev_hash`` matches the previous receipt's ``hash``.
3. ``hash`` == SHA-256 of canonical-JSON(``body``).
4. ``sig`` is a valid Ed25519 signature over the hex ``hash`` string.

SHA-256 comes from ``window.crypto.subtle``; Ed25519 verification uses the
``Ed25519`` key type that is now part of WebCrypto Level 2 (Chrome 113+, Edge,
Safari 17+, Firefox 130+). For older browsers the page falls back to displaying
the receipt list with a clear "signature not verified in this browser" notice
rather than silently passing.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable
from typing import Any


def export_proof_link(
    receipts: Iterable[Any],
    *,
    public_key_hex: str,
    run_id: str | None = None,
) -> str:
    """Return a single HTML document verifying the chain (optionally one run)."""
    selected = [r for r in receipts if run_id is None or r.body.run_id == run_id]
    payload = [
        {
            "body": r.body.model_dump(mode="json"),
            "hash": r.hash,
            "sig": r.sig,
        }
        for r in selected
    ]
    return _PROOF_HTML_TEMPLATE.format(
        public_key_hex=html.escape(public_key_hex),
        run_label=html.escape(run_id or "(full chain)"),
        receipts_json=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        receipt_count=len(payload),
    )


_PROOF_HTML_TEMPLATE = """<!doctype html>

<html lang="en">
<head>
<meta charset="utf-8" />
<title>MIDAS Proof Link</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {{ color-scheme: light dark; }}
  html, body {{ font-family: -apple-system, Segoe UI, system-ui, sans-serif; margin: 0; padding: 2rem 1.25rem; }}
  body {{ max-width: 880px; margin: 0 auto; line-height: 1.55; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .25rem; }}
  .meta {{ color: #6b7280; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .badge {{ display: inline-block; padding: 4px 10px; font-family: ui-monospace, monospace; font-size: 12px; border: 1px solid currentColor; border-radius: 0; }}
  .ok {{ color: #2a4d3a; }}
  .fail {{ color: #b91c1c; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1.25rem; font-family: ui-monospace, monospace; font-size: 12px; }}
  th, td {{ text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #e5e7eb; }}
  th {{ color: #6b7280; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; font-size: 11px; }}
  details {{ margin-top: 1rem; font-family: ui-monospace, monospace; font-size: 12px; }}
  details pre {{ overflow: auto; max-height: 240px; background: #f9fafb; padding: .5rem .75rem; }}
  footer {{ margin-top: 2rem; color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<h1>MIDAS Proof Link</h1>
<div class="meta">run: {run_label} · receipts: {receipt_count}</div>
<div class="meta">public key: {public_key_hex}</div>
<div id="verdict" class="badge" style="margin-top: 1rem;">Verifying chain…</div>
<table id="rows"><thead>
  <tr><th>seq</th><th>ts</th><th>tool</th><th>decision</th><th>hash</th></tr>
</thead><tbody></tbody></table>
<details><summary>Raw receipts (JSONL)</summary><pre id="raw"></pre></details>
<footer>
  No installation required. The chain is verified in your browser using SHA-256
  and Ed25519 (WebCrypto). Re-open this file offline — the verification is
  identical.
</footer>
<script id="payload" type="application/json">{receipts_json}</script>
<script>
(function() {{
  const RECEIPTS = JSON.parse(document.getElementById('payload').textContent);
  const PUB_HEX = "{public_key_hex}";
  const verdictEl = document.getElementById('verdict');
  const rowsEl = document.querySelector('#rows tbody');
  const rawEl = document.getElementById('raw');
  rawEl.textContent = RECEIPTS.map(r => JSON.stringify(r)).join("\\n");
  function hexToBytes(h) {{
    const out = new Uint8Array(h.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(i * 2, 2), 16);
    return out;
  }}
  function bytesToHex(b) {{
    return Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
  }}
  function canonicalJson(value) {{
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
    const keys = Object.keys(value).sort();
    return '{{' + keys.map(k => JSON.stringify(k) + ':' + canonicalJson(value[k])).join(',') + '}}';
  }}
  async function sha256Hex(input) {{
    const enc = new TextEncoder().encode(input);
    const digest = await crypto.subtle.digest('SHA-256', enc);
    return bytesToHex(new Uint8Array(digest));
  }}
  async function verifyEd25519(pubHex, message, sigHex) {{
    if (!crypto.subtle || !crypto.subtle.importKey) return null;
    try {{
      const key = await crypto.subtle.importKey(
        'raw', hexToBytes(pubHex), {{ name: 'Ed25519' }}, false, ['verify']
      );
      const sig = hexToBytes(sigHex);
      const msg = new TextEncoder().encode(message);
      return await crypto.subtle.verify({{ name: 'Ed25519' }}, key, sig, msg);
    }} catch (e) {{
      return null;
    }}
  }}
  function renderRow(receipt) {{
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + receipt.body.seq + '</td>' +
      '<td>' + receipt.body.ts + '</td>' +
      '<td>' + receipt.body.tool + '</td>' +
      '<td>' + receipt.body.decision + '</td>' +
      '<td>' + receipt.hash.slice(0, 24) + '…</td>';
    rowsEl.appendChild(tr);
  }}
  (async () => {{
    let prev = '0'.repeat(64);
    let sigSupported = true;
    for (let i = 0; i < RECEIPTS.length; i++) {{
      const r = RECEIPTS[i];
      renderRow(r);
      if (r.body.seq !== i) {{
        verdictEl.textContent = 'FAIL — seq mismatch at index ' + i;
        verdictEl.classList.add('fail'); return;
      }}
      if (r.body.prev_hash !== prev) {{
        verdictEl.textContent = 'FAIL — prev_hash break at seq ' + i;
        verdictEl.classList.add('fail'); return;
      }}
      const recomputed = await sha256Hex(canonicalJson(r.body));
      if (recomputed !== r.hash) {{
        verdictEl.textContent = 'FAIL — hash mismatch at seq ' + i;
        verdictEl.classList.add('fail'); return;
      }}
      const sigOk = await verifyEd25519(PUB_HEX, r.hash, r.sig);
      if (sigOk === false) {{
        verdictEl.textContent = 'FAIL — bad signature at seq ' + i;
        verdictEl.classList.add('fail'); return;
      }}
      if (sigOk === null) sigSupported = false;
      prev = r.hash;
    }}
    if (sigSupported) {{
      verdictEl.textContent = 'OK — ' + RECEIPTS.length + ' receipt(s) verified.';
      verdictEl.classList.add('ok');
    }} else {{
      verdictEl.textContent =
        'PARTIAL — chain + hashes OK; Ed25519 signature not verifiable in this browser.';
    }}
  }})();
}})();
</script>
</body>
</html>
"""
