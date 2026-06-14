"""End-to-end flagship flows."""

from .discover import discover_candidates, gather_evidence, parse_candidates, verify_candidates
from .opportunity_scan import DEFAULT_MIN_PROOF, run_scan, scan_niche

__all__ = [
    "run_scan",
    "scan_niche",
    "discover_candidates",
    "parse_candidates",
    "verify_candidates",
    "gather_evidence",
    "DEFAULT_MIN_PROOF",
]
