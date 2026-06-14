# Security Policy

The full security model is documented in [docs/SECURITY.md](docs/SECURITY.md) and
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Reporting

Please do not publish exploitable security issues before maintainers have time to
respond. Open a private report through GitHub Security Advisories when the repository
is published, or contact the maintainer through the project profile.

Include:

- affected version or commit;
- reproduction steps;
- expected vs actual behavior;
- impact;
- whether secrets, PII, money, external sends, or filesystem writes are involved.

## Security Defaults

- Local-first runtime.
- Dashboard bound to loopback only.
- Human approval for risky actions.
- Hash-chained receipts.
- Budget fuse.
- Source verification.
- Remote skill downloads are approval-gated.

MIDAS is aligned with emerging audit/provenance best practices. It is not certified
or guaranteed compliant with any security, legal, or regulatory framework.
