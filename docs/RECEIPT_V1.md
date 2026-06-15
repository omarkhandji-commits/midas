# Receipt v1 — Verifiable Execution Spec

**Status:** v1 (frozen). Breaking changes ship as `v2`.
**Reference implementation:** [`midas.core.receipts`](../src/midas/core/receipts).
**Independent verifier:** [`tools/verify/midas_verify`](../tools/verify) — `pip install pynacl`, then `python -m midas_verify <ledger.jsonl> --public-key <hex>`.

Receipt v1 is a compact, append-only, hash-chained, Ed25519-signed JSONL log of every
tool/LLM action an agent takes. It is **independently verifiable**: anyone with the
public key and the ledger file can prove (or disprove) that the chain was produced by
the holder of the private key and was never edited after the fact. No trust in the
agent runtime required.

## Goals

1. **Tamper evidence.** Flipping a single byte anywhere in the file is detectable.
2. **Portability.** A 100-line verifier in any language with Ed25519 + SHA-256 + JSON
   can audit the chain.
3. **Privacy.** Inputs and outputs are stored as SHA-256 digests, never raw content.
4. **Provenance.** Every record names the agent, the tool, and the decision (allowed,
   queued for approval, or denied).

## Non-goals

- Not a blockchain: no consensus, no peers. One signer per ledger.
- Not encryption: receipts are public-readable; secrecy is delivered by hashing payloads.
- Not "compliance" or a legal artifact. The spec describes what the bytes mean; no claim
  is made about regulatory acceptance.

## File format

A receipt ledger is a UTF-8 text file with **one receipt per line** (JSONL). Empty
lines are ignored. The order of lines is the order of events.

## Receipt structure

Each line is a JSON object with exactly three fields:

```json
{
  "body": { ...ReceiptBody... },
  "hash": "<sha256 hex of canonical(body)>",
  "sig":  "<Ed25519 signature over hash, hex>"
}
```

### `body` fields

| Field         | Type    | Description                                                      |
|---------------|---------|------------------------------------------------------------------|
| `seq`         | int     | 0-based monotonic position in this ledger.                       |
| `prev_hash`   | string  | Hex SHA-256 of the previous receipt's body. `"0" * 64` for `seq=0`. |
| `ts`          | string  | ISO-8601 UTC timestamp of the event.                             |
| `run_id`      | string  | Opaque correlation id grouping a multi-step run.                 |
| `agent`       | string  | Agent name that produced the event.                              |
| `tool`        | string  | Tool or action name (e.g. `email.draft`, `research.search`).     |
| `decision`    | enum    | `allow` \| `queue_approval` \| `deny`.                           |
| `inputs_hash` | string  | Hex SHA-256 of `canonical_json(inputs)`. Never the raw inputs.   |
| `outputs_hash`| string  | Hex SHA-256 of `canonical_json(outputs)`. Never the raw outputs. |
| `cost_usd`    | number  | Spend incurred by this step. `0.0` if none.                      |
| `taint_in`    | enum    | `trusted` \| `untrusted` \| `private`.                           |
| `taint_out`   | enum    | `trusted` \| `untrusted` \| `private`.                           |
| `approval_id` | string\|null | Id of the human approval that authorized this step, if any. |

Unknown future fields MUST be rejected by a v1 verifier — `v2` is the proper extension
path.

## Canonicalization rule

Whenever the body is hashed or signed, it MUST first be serialized as
**canonical JSON**:

- Keys sorted lexicographically at every nesting level.
- No whitespace (`separators=(",", ":")`).
- `ensure_ascii=False`.
- Encoded as UTF-8 bytes.

```python
canonical_json(obj) = json.dumps(
    obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
)
```

## Hash rule

```
body_hash = sha256_hex( canonical_json(body).encode("utf-8") )
```

Because `body` already contains both `seq` and `prev_hash`, the hash binds the receipt
to its exact chain position. Reordering, inserting, or removing any receipt invalidates
all subsequent hashes.

## Signature rule

```
sig = ed25519_sign(private_key, body_hash.encode("utf-8"))
```

The signature is encoded as hex. The verifier MUST verify the signature **over the hex
string of `body_hash`**, not over the raw 32-byte digest. (This matches the reference
implementation in [`Signer.sign`](../src/midas/core/receipts/signer.py) and keeps the
signed message human-readable.)

## Chain rule

For receipt `i`:

- `body.seq == i`.
- `body.prev_hash == hash(receipt[i-1])` if `i > 0`, else `"0" * 64`.
- `sha256_hex(canonical_json(body)) == receipt.hash`.
- `ed25519_verify(public_key, receipt.hash, receipt.sig) == True`.

A verifier MUST stop at the first violation and report `(error, bad_seq)`.

## Getting the public key

```bash
midas keys export-public
```

prints the hex public key of the local MIDAS install. The public key is safe to share;
the secret (Ed25519 seed) is stored in the OS keychain (production) or under
`<state_dir>/signing.key` (file fallback) and is never logged, returned by any API, or
placed into model context.

## Test vectors

The following three lines are a valid Receipt v1 ledger produced with the deterministic
seed `00 * 32`:

**Public key (hex):**
```
3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29
```

**Ledger (`tests/fixtures/receipts_v1_vector.jsonl`):**
```json
{"body":{"seq":0,"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","ts":"2026-01-01T00:00:00+00:00","run_id":"vec-001","agent":"demo","tool":"research.search","decision":"allow","inputs_hash":"985658aa5eae1f3e32f7f3657e2da557996e7ed2717d2571e72eaacf275678e4","outputs_hash":"4d47bc18b3d4a26f87960e0d846fcd94226be47d24b1fac86da7bf40ef6bb24e","cost_usd":0.0,"taint_in":"trusted","taint_out":"untrusted","approval_id":null},"hash":"fc816d989d68978837134ef8ae224afa929163f676617b6037e849f9e0920e39","sig":"9686ef6d8cec5d84ced6441bcccad209b64659632fc0d2741eeb3f1eed289caed79c65cc377a9050ec49ce58ab04d87ec17d7944672822f4e23a336f0c490e0e"}
{"body":{"seq":1,"prev_hash":"fc816d989d68978837134ef8ae224afa929163f676617b6037e849f9e0920e39","ts":"2026-01-01T00:00:01+00:00","run_id":"vec-001","agent":"demo","tool":"email.draft","decision":"queue_approval","inputs_hash":"e386ddc585834f620db7bec5405e42753499488df427f1bc1800f9e8d022c13d","outputs_hash":"80cf7b69386a871ed08a0f73b8ba78390ba8df1c5af15fbda4a13d12c4d54c08","cost_usd":0.001,"taint_in":"trusted","taint_out":"trusted","approval_id":"apv-7"},"hash":"d7376eedbe095fe4c999e8a773f013159c955b3f9ae57364a9ba2e8c13687f7b","sig":"b0cb2e72fa814083aa94803e2d85b5ab627249dbfc6324634f36de15904a8aef021af12a9f271c68383ab976849fda3ba1d43d660cef483f9ff7bf6ba666560c"}
{"body":{"seq":2,"prev_hash":"d7376eedbe095fe4c999e8a773f013159c955b3f9ae57364a9ba2e8c13687f7b","ts":"2026-01-01T00:00:02+00:00","run_id":"vec-001","agent":"demo","tool":"email.send","decision":"deny","inputs_hash":"80cf7b69386a871ed08a0f73b8ba78390ba8df1c5af15fbda4a13d12c4d54c08","outputs_hash":"a9c6b7a70bccb39dccb6b023261990c377da2cafd137ce65d11c5bd9b351560c","cost_usd":0.0,"taint_in":"trusted","taint_out":"trusted","approval_id":"apv-7"},"hash":"0f97a3b45261fac532ccd78ef51fc994cbf941caf975da8b55905d904418cea9","sig":"45fd90370bd3d898bc8cb0322f4e0d26361c205bf148aff3422242d3c41748929976d7d4cd767f4e7afb3b185d49dd2ee2bbb79963a01cdf88f154589f181e0b"}
```

A conforming verifier MUST report `OK — 3 receipt(s) verified.` for this input.
Flipping any single byte (e.g. changing `"allow"` to `"deny"` in seq 0) MUST report
failure at `seq 0`.

## Versioning

`v1` is frozen. Additional fields, alternative signing schemes, or canonicalization
changes require `v2` with an explicit version tag in each record. Verifiers reading a
`v2` ledger SHOULD refuse to process it as `v1`.

## Disclaimers

- This spec describes a tamper-evident audit trail. It does not by itself make any
  application "secure", "compliant", or "certified" — those are organizational
  claims, not cryptographic ones.
- The signing key's security is whatever the OS keychain (or chosen storage) provides.
- Receipts prove *what the agent did*, not whether what it did was correct.
