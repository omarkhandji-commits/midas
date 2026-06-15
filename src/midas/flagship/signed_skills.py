"""Signed shareable skill bundles — Ed25519 over canonical-JSON manifest.

A signed bundle is a directory containing the skill's files plus a `manifest.json`
listing every relative path with its sha256, and a `manifest.sig` carrying:

    {
      "manifest_sha256": "<sha256 hex of canonical-JSON manifest>",
      "public_key_hex": "<Ed25519 pub key, hex>",
      "signature": "<hex Ed25519 signature over manifest_sha256>"
    }

Verification (no MIDAS state required):

1. Recompute every file's sha256 → compare to manifest.
2. Recompute the canonical-JSON sha256 of manifest → compare to ``manifest_sha256``.
3. Ed25519-verify ``signature`` over ``manifest_sha256`` with ``public_key_hex``.

Approval-default still applies: a verified bundle is INSTALLED only after
``ApprovalQueue`` resolution by the operator, reusing the existing
``SkillRegistry.install_local`` path (executable-payload rejection + 2 MB cap).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from midas.core.receipts.models import canonical_json
from midas.core.receipts.signer import Signer


@dataclass(frozen=True)
class SignedManifest:
    name: str
    version: str
    summary: str
    files: dict[str, str]  # relative path → sha256 hex


@dataclass(frozen=True)
class BundleSignature:
    manifest_sha256: str
    public_key_hex: str
    signature: str


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    error: str | None = None
    manifest: SignedManifest | None = None
    public_key_hex: str | None = None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _walk_files(source: Path) -> list[Path]:
    return sorted(p for p in source.rglob("*") if p.is_file())


def export_signed_skill(
    source: str | Path,
    destination: str | Path,
    signer: Signer,
    *,
    name: str,
    version: str = "0.1.0",
    summary: str = "",
) -> Path:
    """Write a signed bundle (directory) at ``destination``.

    The destination is overwritten if it exists. Returns the destination path.
    """
    src = Path(source)
    if not src.is_dir():
        raise ValueError(f"signed-skill source must be a directory: {src}")
    skill_md = src / "SKILL.md"
    if not skill_md.exists():
        raise ValueError("signed-skill source must contain SKILL.md")

    dst = Path(destination)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # Write the legacy skill.json BEFORE computing the manifest hashes so it
    # participates in the signature. SkillRegistry.install_local reads this file
    # to recover the canonical name/version/summary.
    (dst / "skill.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "summary": summary,
                "permissions": ["read"],
                "source": "signed-bundle",
                "sha256": "",  # placeholder — sha is in manifest.sig
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    files: dict[str, str] = {}
    for path in _walk_files(dst):
        rel = path.relative_to(dst).as_posix()
        if rel in {"manifest.json", "manifest.sig"}:
            continue
        files[rel] = _sha256_bytes(path.read_bytes())

    manifest = SignedManifest(name=name, version=version, summary=summary, files=files)
    manifest_json = canonical_json(asdict(manifest))
    manifest_sha = _sha256_bytes(manifest_json.encode("utf-8"))
    signature = signer.sign(manifest_sha)

    (dst / "manifest.json").write_text(manifest_json, encoding="utf-8")
    (dst / "manifest.sig").write_text(
        json.dumps(
            {
                "manifest_sha256": manifest_sha,
                "public_key_hex": signer.public_key_hex,
                "signature": signature,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return dst


def verify_signed_skill(bundle: str | Path) -> VerifyResult:
    """Verify the bundle. Returns ``VerifyResult`` — never raises on bad input."""
    bdir = Path(bundle)
    manifest_path = bdir / "manifest.json"
    sig_path = bdir / "manifest.sig"
    if not (manifest_path.exists() and sig_path.exists()):
        return VerifyResult(ok=False, error="missing manifest.json or manifest.sig")

    try:
        manifest_raw = manifest_path.read_text(encoding="utf-8")
        manifest = SignedManifest(**json.loads(manifest_raw))
        sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure = invalid bundle
        return VerifyResult(ok=False, error=f"parse error: {exc}")

    bundle_sig = BundleSignature(
        manifest_sha256=str(sig_data.get("manifest_sha256") or ""),
        public_key_hex=str(sig_data.get("public_key_hex") or ""),
        signature=str(sig_data.get("signature") or ""),
    )

    # 1. File hashes must match the manifest.
    actual_files: dict[str, str] = {}
    for path in _walk_files(bdir):
        rel = path.relative_to(bdir).as_posix()
        if rel in {"manifest.json", "manifest.sig"}:
            continue
        actual_files[rel] = _sha256_bytes(path.read_bytes())
    if actual_files != manifest.files:
        return VerifyResult(ok=False, error="file hash mismatch", manifest=manifest)

    # 2. Canonical-JSON sha256 of manifest must match the sig record.
    recomputed = _sha256_bytes(canonical_json(asdict(manifest)).encode("utf-8"))
    if recomputed != bundle_sig.manifest_sha256:
        return VerifyResult(ok=False, error="manifest sha256 mismatch", manifest=manifest)

    # 3. Ed25519 verify.
    if not Signer.verify(
        bundle_sig.public_key_hex, bundle_sig.manifest_sha256, bundle_sig.signature
    ):
        return VerifyResult(ok=False, error="bad signature", manifest=manifest)

    return VerifyResult(
        ok=True, manifest=manifest, public_key_hex=bundle_sig.public_key_hex
    )


def import_signed_skill(
    bundle: str | Path,
    registry: Any,
) -> dict[str, Any]:
    """Verify then route through ``SkillRegistry.install_local`` — same gates apply.

    Raises if the signature does not verify. The caller is expected to have
    cleared an approval beforehand (this function does NOT enqueue).
    """
    result = verify_signed_skill(bundle)
    if not result.ok:
        raise PermissionError(f"signed-skill verification failed: {result.error}")
    manifest = registry.install_local(bundle)
    return {
        "name": manifest.name,
        "version": manifest.version,
        "summary": manifest.summary,
        "tree_sha256": manifest.sha256,
        "signer_public_key_hex": result.public_key_hex,
    }
