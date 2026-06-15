"""Standalone Receipt v1 verifier. PyNaCl + stdlib only — no midas.* imports."""

from .verify import VerifyResult, verify_chain

__all__ = ["VerifyResult", "verify_chain"]
__version__ = "1.0.0"
