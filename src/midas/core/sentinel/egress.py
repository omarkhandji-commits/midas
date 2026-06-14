"""Egress allow-list (deny-by-default) for automatic outbound transmissions."""

from __future__ import annotations

from collections.abc import Iterable


def domain_allowed(domain: str, allowlist: Iterable[str]) -> bool:
    d = domain.lower().strip().rstrip(".")
    for entry in allowlist:
        a = entry.lower().strip().rstrip(".")
        if not a:
            continue
        if d == a or d.endswith("." + a):  # exact match or subdomain
            return True
    return False


def first_blocked_domain(domains: Iterable[str], allowlist: Iterable[str]) -> str | None:
    allow = list(allowlist)
    for d in domains:
        if not domain_allowed(d, allow):
            return d
    return None
