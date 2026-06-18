"""WS2 — Cash artifact tools: queue + sha256 + executor determinism.

Each new tool must (1) queue an approval (never run inline), (2) carry sha256_new
in the payload, (3) materialize deterministic bytes post-approval.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from midas.core.approvals.queue import ApprovalQueue
from midas.core.config.models import (
    ActionsPolicy,
    ApprovalPolicy,
    AuditPolicy,
    FilesystemPolicy,
    ModelsPolicy,
    PolicyConfig,
    SourcesPolicy,
    SpendCaps,
)
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel import Sentinel
from midas.flagship.agent.registry import build_default_toolset
from midas.flagship.agent.tools.cash import (
    build_adcopy_content,
    build_landing_content,
    build_outreach_content,
    build_product_content,
    build_proposal_content,
    build_quote_content,
    execute_adcopy,
    execute_landing,
    execute_outreach,
    execute_product,
    execute_proposal,
    execute_quote,
    plan_landing,
)
from midas.flagship.agent.tools.fsguard import FsGuard


def _policy() -> PolicyConfig:
    return PolicyConfig(
        autonomy="semi-auto",
        kill_switch="off",
        spend_caps=SpendCaps(),
        models=ModelsPolicy(),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write", "execute_code", "write_spreadsheet"},
            never={"spam"},
        ),
        approval=ApprovalPolicy(),
        egress_allowlist=[],
        filesystem=FilesystemPolicy(workspace_only=True, deny_paths=[]),
        audit=AuditPolicy(),
        sources=SourcesPolicy(),
    )


def _make_toolset(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    guard = FsGuard(workspace=workspace.resolve())
    sentinel = Sentinel(_policy())
    ledger = ReceiptLedger(state / "receipts.jsonl", Signer.from_hex_seed("ca" * 32))
    approvals = ApprovalQueue(state / "approvals.db", ledger=ledger)
    ts = build_default_toolset(
        sentinel=sentinel,
        guard=guard,
        ledger=ledger,
        approvals=approvals,
        run_id="test-cash",
    )
    return ts, approvals, guard


# ── plan-level determinism (each builder is pure) ────────────────────────────


def test_landing_builder_deterministic() -> None:
    a = build_landing_content(
        headline="Get more cake orders this week",
        subheading="Custom cakes in Montréal",
        body="Order by Thursday for Saturday pickup.",
        cta_text="Order now",
    )
    b = build_landing_content(
        headline="Get more cake orders this week",
        subheading="Custom cakes in Montréal",
        body="Order by Thursday for Saturday pickup.",
        cta_text="Order now",
    )
    assert a == b
    assert "<!DOCTYPE html>" in a
    assert "<script" not in a.lower()


def test_landing_rejects_empty_headline() -> None:
    with pytest.raises(ValueError):
        build_landing_content(
            headline="", subheading="", body="", cta_text="Buy",
        )


def test_product_rejects_no_deliverables() -> None:
    with pytest.raises(ValueError):
        build_product_content(
            title="X", audience="", problem="", deliverables=[], price_usd=10,
        )


def test_outreach_rejects_no_steps() -> None:
    with pytest.raises(ValueError):
        build_outreach_content(audience="plumbers", offer="leads", steps=[])


def test_proposal_rejects_no_scope() -> None:
    with pytest.raises(ValueError):
        build_proposal_content(
            client="Acme", project="P", scope=[], price_usd=1000,
        )


def test_quote_rejects_no_items() -> None:
    with pytest.raises(ValueError):
        build_quote_content(client="Acme", items=[])


def test_adcopy_rejects_no_variants() -> None:
    with pytest.raises(ValueError):
        build_adcopy_content(product="x", audience="y", variants=[])


# ── plan helper sets sha256_new from real content ────────────────────────────


def test_plan_landing_sets_sha256(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    guard = FsGuard(workspace=workspace.resolve())
    plan = plan_landing(
        guard,
        "landing.html",
        headline="Hello",
        cta_text="Buy",
    )
    expected_content = build_landing_content(
        headline="Hello", subheading="", body="", cta_text="Buy", cta_href="#",
    )
    expected_sha = hashlib.sha256(expected_content.encode("utf-8")).hexdigest()
    assert plan.sha256_new == expected_sha
    assert plan.bytes_len == len(expected_content.encode("utf-8"))
    assert plan.path.endswith("landing.html")


# ── invoke through Toolset → APPROVE-tier queue, never inline ─────────────────


def test_landing_draft_queues_approval_does_not_write(tmp_path: Path) -> None:
    ts, approvals, guard = _make_toolset(tmp_path)
    target = guard.workspace / "out.html"
    outcome = ts.invoke(
        "landing.draft",
        agent="test",
        path="out.html",
        headline="Cakes today",
        cta_text="Order",
    )
    assert outcome.ran is False
    assert outcome.approval_id is not None
    assert outcome.verdict.decision.value == "queue_approval"
    assert not target.exists()  # critical: no write happened
    queued = approvals.get(outcome.approval_id)
    assert queued is not None
    assert queued.payload["sha256_new"]
    assert queued.payload["preview"].startswith("Cakes today")


def test_product_draft_queues(tmp_path: Path) -> None:
    ts, _, _ = _make_toolset(tmp_path)
    outcome = ts.invoke(
        "product.draft",
        agent="test",
        path="product.md",
        title="Invoice helper",
        deliverables=["template", "video"],
        price_usd=29.0,
    )
    assert outcome.ran is False
    assert outcome.approval_id is not None


def test_image_voice_and_stripe_queue_exact_planned_payloads(tmp_path: Path) -> None:
    ts, approvals, _ = _make_toolset(tmp_path)
    image = ts.invoke(
        "image.draft",
        agent="test",
        path="hero.png",
        prompt="MIDAS logo on a clean console",
    )
    voice = ts.invoke(
        "voice.synthesize",
        agent="test",
        path="brief.wav",
        text="Bonjour boss, voici le brief.",
    )
    stripe = ts.invoke(
        "stripe.payment_link",
        agent="test",
        description="MIDAS setup",
        amount_usd=49,
        currency="USD",
    )

    for outcome, required in [
        (image, ["sha256_new", "bytes_b64", "bytes_len"]),
        (voice, ["sha256_new", "bytes_b64", "bytes_len"]),
        (stripe, ["sha256_intent", "amount_minor", "currency"]),
    ]:
        assert outcome.approval_id is not None
        req = approvals.get(outcome.approval_id)
        assert req is not None
        for key in required:
            assert req.payload.get(key), (req.tool, key)


def test_code_run_queues_code_hash(tmp_path: Path) -> None:
    ts, approvals, _ = _make_toolset(tmp_path)
    outcome = ts.invoke("code.run", agent="test", code="print('ok')")
    assert outcome.approval_id is not None
    req = approvals.get(outcome.approval_id)
    assert req is not None
    assert req.payload["code_sha256"] == hashlib.sha256(b"print('ok')").hexdigest()


def test_outreach_sequence_queues(tmp_path: Path) -> None:
    ts, _, _ = _make_toolset(tmp_path)
    outcome = ts.invoke(
        "outreach.sequence",
        agent="test",
        path="seq.md",
        audience="plumbers",
        offer="lead gen",
        steps=[{"channel": "email", "subject": "hi", "body": "..."}],
    )
    assert outcome.ran is False
    assert outcome.approval_id is not None


def test_proposal_quote_adcopy_all_queue(tmp_path: Path) -> None:
    ts, _, _ = _make_toolset(tmp_path)
    for name, kwargs in [
        (
            "proposal.draft",
            {
                "path": "p.md",
                "client": "Acme",
                "project": "Site",
                "scope": ["design", "ship"],
                "price_usd": 1200,
            },
        ),
        (
            "quote.draft",
            {
                "path": "q.md",
                "client": "Acme",
                "items": [("Design", 1.0, 600.0), ("Dev", 1.0, 600.0)],
            },
        ),
        (
            "adcopy.draft",
            {
                "path": "a.md",
                "product": "Invoice helper",
                "audience": "freelancers",
                "variants": [{"headline": "Faster invoices", "cta": "Try"}],
            },
        ),
    ]:
        outcome = ts.invoke(name, agent="test", **kwargs)
        assert outcome.ran is False, name
        assert outcome.approval_id is not None, name


# ── post-approval executor rebuilds the exact bytes (determinism) ────────────


def test_executors_match_plan_bytes() -> None:
    """Re-encode == plan bytes (so the operator approves what gets written)."""
    cases = [
        (
            execute_landing,
            {
                "headline": "h",
                "subheading": "s",
                "body": "b",
                "cta_text": "Buy",
                "cta_href": "#",
            },
            build_landing_content,
        ),
        (
            execute_product,
            {
                "title": "X",
                "audience": "y",
                "problem": "z",
                "deliverables": ["a", "b"],
                "price_usd": 19.0,
            },
            build_product_content,
        ),
        (
            execute_outreach,
            {
                "audience": "plumbers",
                "offer": "leads",
                "steps": [{"channel": "email", "subject": "hi", "body": "..."}],
            },
            build_outreach_content,
        ),
        (
            execute_proposal,
            {
                "client": "Acme",
                "project": "Site",
                "scope": ["one"],
                "price_usd": 999.0,
                "timeline": "2w",
                "currency": "USD",
            },
            build_proposal_content,
        ),
        (
            execute_quote,
            {
                "client": "Acme",
                "items": [("Item", 1.0, 100.0)],
                "currency": "USD",
                "quote_number": "Q1",
                "notes": "",
            },
            build_quote_content,
        ),
        (
            execute_adcopy,
            {
                "product": "X",
                "audience": "y",
                "variants": [{"headline": "h", "cta": "c"}],
            },
            build_adcopy_content,
        ),
    ]
    for exec_fn, payload, builder_fn in cases:
        out = exec_fn(payload)
        ref = builder_fn(**payload)
        assert out == ref
