"""Print-on-demand helpers.

The spec tool writes a local product sheet only after approval. The publish tool
creates an approval payload and executes against Printful only after approval and
only when the operator provides PRINTFUL_API_KEY.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifact import ArtifactPlan
from .fsguard import FsGuard


class PodError(RuntimeError):
    """Raised when a POD operation cannot run safely."""


@dataclass
class PodPublishPlan:
    kind: str
    provider: str
    product_spec: dict[str, Any]
    sha256_intent: str
    preview: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PodPublishResult:
    id: str
    provider: str
    raw_status: str


def plan_pod_product_spec(
    guard: FsGuard,
    path: str,
    *,
    title: str,
    design_path: str,
    mockup_url: str = "",
    variants: list[dict[str, Any]] | None = None,
    retail_price: float,
    estimated_cost: float,
    provider: str = "printful",
) -> ArtifactPlan:
    """Create an approval-gated JSON spec sheet for Printful/Printify."""
    if not title.strip():
        raise PodError("pod.product_spec needs a title")
    design = guard.resolve(design_path)
    if not design.exists() or not design.is_file():
        raise PodError("pod.product_spec design_path must exist in the workspace")
    if retail_price < estimated_cost * 1.30:
        raise PodError("pod.product_spec retail_price must be at least cost + 30%")
    target = guard.resolve(path)
    spec = {
        "title": title.strip(),
        "provider": provider.strip().lower() or "printful",
        "design_path": str(design),
        "design_sha256": _sha256(design.read_bytes()),
        "mockup_url": mockup_url.strip(),
        "variants": variants or [],
        "retail_price": round(float(retail_price), 2),
        "estimated_cost": round(float(estimated_cost), 2),
        "margin": round(float(retail_price) - float(estimated_cost), 2),
        "approval_required": True,
    }
    data = json.dumps(spec, indent=2, sort_keys=True).encode("utf-8")
    return ArtifactPlan(
        kind="json",  # type: ignore[arg-type]
        path=str(target),
        bytes_len=len(data),
        sha256_new=_sha256(data),
        sha256_prev=_sha256_file(target),
        preview=f"POD spec: {spec['title']} ({spec['provider']})",
        meta=spec,
    )


def plan_pod_publish_draft(
    *,
    product_spec: dict[str, Any],
    provider: str = "printful",
) -> PodPublishPlan:
    """Build a publish intent. No network, no secret read."""
    clean_provider = provider.strip().lower() or "printful"
    if clean_provider not in {"printful", "printify"}:
        raise PodError("pod.publish_draft provider must be printful or printify")
    if not product_spec.get("title"):
        raise PodError("pod.publish_draft needs a product_spec with title")
    price = float(product_spec.get("retail_price") or 0.0)
    cost = float(product_spec.get("estimated_cost") or 0.0)
    if price < cost * 1.30:
        raise PodError("pod.publish_draft retail_price must be at least cost + 30%")
    intent = {
        "provider": clean_provider,
        "product_spec": product_spec,
    }
    return PodPublishPlan(
        kind="pod_publish",
        provider=clean_provider,
        product_spec=product_spec,
        sha256_intent=_hash_payload(intent),
        preview=f"Publish POD draft to {clean_provider}: {product_spec.get('title')}",
        meta={"retail_price": price, "estimated_cost": cost},
    )


def execute_pod_publish(payload: dict[str, Any]) -> PodPublishResult:
    provider = str(payload.get("provider") or "").lower()
    spec = dict(payload.get("product_spec") or {})
    if provider != "printful":
        raise PodError("only Printful execution is implemented; Printify stays draft-only")
    expected = str(payload.get("sha256_intent") or "")
    got = _hash_payload({"provider": provider, "product_spec": spec})
    if expected and got != expected:
        raise PodError("pod.publish_draft refused: payload intent hash drifted")
    api_key = os.environ.get("PRINTFUL_API_KEY")
    if not api_key:
        raise PodError("Printful publish needs PRINTFUL_API_KEY")
    try:
        import httpx
    except ImportError as e:
        raise PodError("Printful publish needs httpx") from e
    data = {
        "sync_product": {"name": str(spec.get("title") or "")},
        "sync_variants": spec.get("variants") or [],
    }
    try:
        resp = httpx.post(
            "https://api.printful.com/store/products",
            headers={"Authorization": f"Bearer {api_key}"},
            json=data,
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise PodError(f"Printful request failed: {e}") from e
    if resp.status_code not in {200, 201}:
        raise PodError(f"Printful returned {resp.status_code}: {resp.text[:200]}")
    body = resp.json() or {}
    result = body.get("result") or {}
    return PodPublishResult(
        id=str(result.get("id") or ""),
        provider=provider,
        raw_status="printful_ok",
    )


def execute_pod_spec(payload: dict[str, Any]) -> str:
    return json.dumps(payload.get("meta") or {}, indent=2, sort_keys=True)


def _hash_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return _sha256(path.read_bytes())
