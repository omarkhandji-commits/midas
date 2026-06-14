"""MIDAS core — the general, reusable, trustworthy engine.

Modules: router (provider-agnostic LLM), budget (fuse + loop-breaker), receipts
(signed hash-chained ledger), sentinel (security gate), memory, verifier, agents,
channels. None of these may import `midas.flagship`.
"""
