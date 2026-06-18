from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from midas.flagship.agent.tools.cash_ops import (
    build_upsell_sequence,
    compute_cohort_retention,
    compute_referral_payout,
    generate_referral_code,
    transition_customer_lifecycle,
)
from midas.flagship.agent.tools.fsguard import FsGuard
from midas.flagship.agent.tools.pod import plan_pod_product_spec, plan_pod_publish_draft
from midas.flagship.agent.tools.stripe_pay import (
    StripeBackendError,
    execute_price_draft,
    plan_stripe_price_draft,
    plan_stripe_product_draft,
)
from midas.flagship.agent.tools.video import plan_remotion_render


def test_stripe_product_and_price_plans_have_intent_hash() -> None:
    product = plan_stripe_product_draft(
        name="Audit Pack",
        description="One-time business audit",
        metadata={"sku": "audit-pack"},
    )
    assert product.sha256_intent
    assert product.metadata["sku"] == "audit-pack"

    price = plan_stripe_price_draft(
        product="prod_123",
        unit_amount=49.0,
        currency="USD",
        recurring_interval="month",
    )
    assert price.unit_amount_minor == 4900
    assert price.recurring_interval == "month"
    assert price.sha256_intent


def test_stripe_price_execute_refuses_drift() -> None:
    plan = plan_stripe_price_draft(product="prod_123", unit_amount=49.0)
    payload = {
        "product": plan.product,
        "unit_amount_minor": 9900,
        "currency": plan.currency,
        "recurring_interval": plan.recurring_interval,
        "lookup_key": plan.lookup_key,
        "metadata": plan.metadata,
        "sha256_intent": plan.sha256_intent,
    }
    with pytest.raises(StripeBackendError, match="intent hash drifted"):
        execute_price_draft(payload)


def test_pod_spec_requires_design_and_margin(tmp_path: Path) -> None:
    guard = FsGuard(workspace=tmp_path)
    design = tmp_path / "design.png"
    design.write_bytes(b"png")

    spec = plan_pod_product_spec(
        guard,
        "pod/spec.json",
        title="Founder Tee",
        design_path="design.png",
        variants=[{"size": "M", "color": "black"}],
        retail_price=30.0,
        estimated_cost=20.0,
    )
    assert spec.sha256_new
    assert spec.meta["margin"] == 10.0

    with pytest.raises(Exception, match="30%"):
        plan_pod_product_spec(
            guard,
            "pod/spec.json",
            title="Bad",
            design_path="design.png",
            retail_price=21.0,
            estimated_cost=20.0,
        )


def test_pod_publish_plan_hashes_intent() -> None:
    plan = plan_pod_publish_draft(
        product_spec={"title": "Founder Tee", "retail_price": 30, "estimated_cost": 20}
    )
    assert plan.provider == "printful"
    assert plan.sha256_intent


def test_referral_lifecycle_upsell_and_cohorts() -> None:
    code = generate_referral_code("customer@example.com")
    payout = compute_referral_payout(
        code.code, attributed_revenue=1000.0, commission_rate=0.1
    )
    assert payout.payout == 100.0
    assert transition_customer_lifecycle("cust_1", status="won").status == "won"
    upsell = build_upsell_sequence(
        product="Starter Pack", customer_segment="founders", next_offer="Scale Pack"
    )
    assert len(upsell["steps"]) == 3

    cohorts = compute_cohort_retention(
        [
            {"customer_id": "a", "cohort_week": "2026-W25", "active_week": "2026-W25"},
            {"customer_id": "a", "cohort_week": "2026-W25", "active_week": "2026-W26"},
        ]
    ).as_dict()
    assert cohorts["cohorts"][0]["retention"][1]["retention"] == 1.0


def test_remotion_render_plan_hashes_project_zip(tmp_path: Path) -> None:
    guard = FsGuard(workspace=tmp_path)
    project = tmp_path / "project.zip"
    with ZipFile(project, "w") as zf:
        zf.writestr("package.json", "{}")
    plan = plan_remotion_render(
        guard,
        project_zip="project.zip",
        output_path="out/video.mp4",
    )
    assert plan.sha256_project
    assert plan.sha256_intent
    assert plan.output_path.endswith("video.mp4")
