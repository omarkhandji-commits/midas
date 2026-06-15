# midas-verify — Receipt v1 standalone verifier

A 100-line independent verifier for **Receipt v1** ledgers. Depends only on
[`pynacl`](https://pypi.org/project/pynacl/) and the Python standard library.

**Why standalone?** A verifier you can run without trusting MIDAS is the whole point
of verifiable execution. Anyone can audit a MIDAS receipt chain from a fresh venv.

## Install

```bash
pip install pynacl
# then copy this folder anywhere, or:
pip install .
```

## Use

```bash
python -m midas_verify <ledger.jsonl> --public-key <hex>
```

The public key for a MIDAS install comes from:

```bash
midas keys export-public
```

## Exit codes

- `0` — every receipt validates: sequence, prev-hash chain, Ed25519 signature.
- `1` — first failing receipt is reported with its `seq`.

## Spec

See [`docs/RECEIPT_V1.md`](../../docs/RECEIPT_V1.md) for the wire format, canonicalization
rule, signing scheme, and conformance test vectors.
