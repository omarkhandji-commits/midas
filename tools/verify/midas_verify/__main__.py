"""CLI: python -m midas_verify <ledger.jsonl> --public-key <hex>"""

from __future__ import annotations

import argparse
import sys

from .verify import verify_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="midas-verify",
        description="Verify a MIDAS Receipt v1 JSONL ledger using only pynacl + stdlib.",
    )
    parser.add_argument("ledger", help="Path to the JSONL receipt ledger.")
    parser.add_argument(
        "--public-key",
        required=True,
        help="Ed25519 public key (hex). Obtain via `midas keys export-public`.",
    )
    args = parser.parse_args(argv)

    result = verify_chain(args.ledger, args.public_key)
    if result.ok:
        print(f"OK — {result.count} receipt(s) verified.")
        return 0
    print(
        f"FAIL — {result.error or 'verification failed'} "
        f"(after {result.count} OK, bad_seq={result.bad_seq}).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
