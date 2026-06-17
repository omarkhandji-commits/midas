"""email.deliverability_check — honest SPF/DKIM/DMARC posture report.

Why
---
Drafting beautiful outreach emails is wasted work if they land in spam.
SPF, DKIM, and DMARC are the three DNS records that decide whether a
mailbox like Gmail or Outlook will *deliver* the message. This tool
queries the domain's DNS, parses the records, and returns a posture
report with a score and concrete fix recommendations.

Contract
--------
- AUTO-tier (``read_local_files`` action with ``has_egress=True``). DNS
  is a network read, no mutation, no auth.
- Returns: ``{spf: {...}, dkim: {...}, dmarc: {...}, score: 0-100,
  recommendations: [...], proof_level: "MEDIUM"}``.
- ``proof_level=MEDIUM`` because we cite the actual DNS records we read.
  We never fabricate findings.

Honest constraints
------------------
- DKIM is selector-based. There is no "list all selectors" lookup — we
  probe the common defaults (``default``, ``google``, ``selector1``,
  ``selector2``, ``mxvault``, ``s1``, ``s2``, ``k1``, ``k2``, ``dkim``).
  An absent record doesn't mean DKIM is broken — operators with custom
  selectors should pass ``dkim_selectors`` explicitly.
- Score is heuristic, not normative. A low score means "almost certainly
  going to spam"; a high score means "the basics are in place". Real
  deliverability also depends on warmup, content, reputation.
- We do NOT send a probe email. This is DNS-only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


class DeliverabilityError(RuntimeError):
    """Raised when the DNS check can't run honestly."""


_DEFAULT_DKIM_SELECTORS = (
    "default", "google", "selector1", "selector2",
    "mxvault", "s1", "s2", "k1", "k2", "dkim",
)


@dataclass
class SpfRecord:
    found: bool
    raw: str = ""
    has_all: bool = False
    has_minus_all: bool = False
    has_redirect: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class DkimRecord:
    found: bool
    selectors_found: list[str] = field(default_factory=list)
    selectors_checked: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DmarcRecord:
    found: bool
    raw: str = ""
    policy: str = ""  # none / quarantine / reject
    has_rua: bool = False
    pct: int = 100
    notes: list[str] = field(default_factory=list)


@dataclass
class DeliverabilityReport:
    domain: str
    spf: SpfRecord
    dkim: DkimRecord
    dmarc: DmarcRecord
    score: int  # 0..100
    proof_level: str  # always "MEDIUM" — sourced from DNS
    recommendations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "spf": asdict(self.spf),
            "dkim": asdict(self.dkim),
            "dmarc": asdict(self.dmarc),
            "score": self.score,
            "proof_level": self.proof_level,
            "recommendations": self.recommendations,
        }


def _txt_query(name: str) -> list[str]:
    """Return TXT record strings for ``name``. Empty list on any failure."""
    try:
        import dns.resolver
    except ImportError as e:
        raise DeliverabilityError(
            "email.deliverability_check needs dnspython; "
            "install with `pip install dnspython`"
        ) from e
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5.0)
    except Exception:
        return []
    out: list[str] = []
    for rdata in answers:
        # dnspython TXT rdata: list of byte strings (one TXT record per fragment).
        parts = getattr(rdata, "strings", None)
        if parts:
            try:
                out.append(b"".join(parts).decode("utf-8", errors="replace"))
            except Exception:
                out.append(str(rdata))
        else:
            out.append(str(rdata).strip('"'))
    return out


def _parse_spf(records: list[str]) -> SpfRecord:
    for raw in records:
        if raw.lower().startswith("v=spf1"):
            tokens = raw.split()
            has_all = any(t.lower().endswith("all") for t in tokens)
            has_minus_all = any(t == "-all" for t in tokens)
            has_redirect = any(t.startswith("redirect=") for t in tokens)
            notes: list[str] = []
            if not has_all and not has_redirect:
                notes.append("SPF policy has no terminator (-all / ~all / redirect)")
            if not has_minus_all and not has_redirect:
                notes.append(
                    "SPF uses a soft fail or no fail — receivers may still accept "
                    "spoofed mail; consider -all once you're confident in includes"
                )
            return SpfRecord(
                found=True,
                raw=raw,
                has_all=has_all,
                has_minus_all=has_minus_all,
                has_redirect=has_redirect,
                notes=notes,
            )
    return SpfRecord(found=False)


def _parse_dmarc(records: list[str]) -> DmarcRecord:
    for raw in records:
        if not raw.lower().startswith("v=dmarc1"):
            continue
        parts = {
            kv.split("=", 1)[0].strip().lower(): kv.split("=", 1)[1].strip()
            for kv in raw.split(";") if "=" in kv
        }
        policy = parts.get("p", "").lower()
        pct_raw = parts.get("pct", "100")
        try:
            pct = int(pct_raw)
        except ValueError:
            pct = 100
        notes: list[str] = []
        if policy == "none":
            notes.append(
                "DMARC policy is 'none' — receivers won't enforce; "
                "use 'quarantine' or 'reject' once SPF+DKIM are stable"
            )
        if pct < 100:
            notes.append(
                f"DMARC pct={pct}% — only that share of failing mail is enforced"
            )
        return DmarcRecord(
            found=True,
            raw=raw,
            policy=policy,
            has_rua="rua" in parts,
            pct=pct,
            notes=notes,
        )
    return DmarcRecord(found=False)


def _probe_dkim(domain: str, selectors: list[str]) -> DkimRecord:
    found_sels: list[str] = []
    checked: list[str] = []
    for sel in selectors:
        sel = sel.strip()
        if not sel:
            continue
        checked.append(sel)
        records = _txt_query(f"{sel}._domainkey.{domain}")
        for raw in records:
            if raw.lower().startswith(("v=dkim1", "k=", "p=")):
                found_sels.append(sel)
                break
    notes: list[str] = []
    if not found_sels:
        notes.append(
            "no DKIM record found at any common selector; "
            "pass dkim_selectors=[...] if you use a custom one"
        )
    return DkimRecord(
        found=bool(found_sels),
        selectors_found=found_sels,
        selectors_checked=checked,
        notes=notes,
    )


def _compute_score(
    spf: SpfRecord, dkim: DkimRecord, dmarc: DmarcRecord
) -> tuple[int, list[str]]:
    """Heuristic 0..100. Honest: this is a proxy, not a guarantee."""
    score = 0
    recs: list[str] = []
    if spf.found:
        score += 30
        if spf.has_minus_all:
            score += 5
        else:
            recs.append(
                "Tighten SPF: end the record with -all once your includes are stable."
            )
    else:
        recs.append("Publish an SPF TXT record at the apex (v=spf1 include:… -all).")
    if dkim.found:
        score += 30
    else:
        recs.append(
            "Publish a DKIM key and align it with your sending platform "
            "(Google: 'google._domainkey'; Microsoft: 'selector1/2._domainkey')."
        )
    if dmarc.found:
        score += 20
        if dmarc.policy in {"quarantine", "reject"}:
            score += 10
        else:
            recs.append(
                "Strengthen DMARC: move from p=none to p=quarantine, then p=reject."
            )
        if dmarc.has_rua:
            score += 5
        else:
            recs.append(
                "Add 'rua=mailto:dmarc@yourdomain' to DMARC so you receive aggregate reports."
            )
    else:
        recs.append("Publish DMARC at _dmarc.<domain> (v=DMARC1; p=none; rua=mailto:…).")
    score = min(100, max(0, score))
    return score, recs


def check_deliverability(
    domain: str, *, dkim_selectors: list[str] | None = None
) -> DeliverabilityReport:
    """DNS-only deliverability posture check."""
    domain = domain.strip().lower()
    if not domain or "." not in domain:
        raise DeliverabilityError(
            f"email.deliverability_check needs a real domain, got {domain!r}"
        )
    if domain.startswith(("@", "http://", "https://")):
        raise DeliverabilityError(
            "pass a bare domain (example.com), not an email or URL"
        )

    spf = _parse_spf(_txt_query(domain))
    dmarc = _parse_dmarc(_txt_query(f"_dmarc.{domain}"))
    selectors = list(dkim_selectors) if dkim_selectors else list(_DEFAULT_DKIM_SELECTORS)
    dkim = _probe_dkim(domain, selectors)
    score, recs = _compute_score(spf, dkim, dmarc)
    return DeliverabilityReport(
        domain=domain,
        spf=spf,
        dkim=dkim,
        dmarc=dmarc,
        score=score,
        proof_level="MEDIUM",
        recommendations=recs,
    )
