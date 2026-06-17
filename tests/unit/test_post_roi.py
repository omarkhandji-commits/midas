"""Per-post ROI — joins ``platform:post_id``-tagged receipts to outcomes.

Proof-First applies: cost comes from the signed chain, revenue from the
operator's recorded outcomes. A post with no outcome shows ``revenue=0`` and
no ratio — we never invent a number that isn't in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from midas.flagship.roi import (
    PostRoi,
    PostRoiReport,
    build_post_outcomes_index,
    compute_post_roi,
)


@dataclass
class _Body:
    run_id: str
    cost_usd: float
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Receipt:
    body: _Body


def _r(run_id: str, cost: float, **outputs: Any) -> _Receipt:
    return _Receipt(body=_Body(run_id=run_id, cost_usd=cost, outputs=outputs))


def test_compute_post_roi_groups_by_platform_and_post_id() -> None:
    receipts = [
        _r("run-1", 0.10, platform="instagram", post_id="ABC", account_handle="@brand"),
        _r("run-1", 0.05, platform="instagram", post_id="ABC", account_handle="@brand"),
        _r("run-2", 0.20, platform="x", post_id="999", account_handle="@brand_x"),
        _r("run-3", 0.50, platform="instagram", post_id="OTHER", account_handle="@brand"),
    ]
    outcomes = {
        "instagram:ABC": {
            "platform": "instagram",
            "account_handle": "@brand",
            "revenue_usd": 100.0,
            "sources": ["https://shop.example/order/1"],
        }
    }

    report = compute_post_roi(receipts, outcomes)

    by_key = {p.post_key: p for p in report.posts}
    assert set(by_key) == {"instagram:ABC", "instagram:OTHER", "x:999"}
    ig_abc = by_key["instagram:ABC"]
    assert ig_abc.cost_usd == 0.15
    assert ig_abc.revenue_usd == 100.0
    assert ig_abc.net_usd == 99.85
    assert ig_abc.sources == ["https://shop.example/order/1"]
    assert ig_abc.receipt_count == 2

    other = by_key["instagram:OTHER"]
    assert other.revenue_usd == 0.0  # no outcome → never invented
    assert other.roi_ratio is None or other.roi_ratio == 0.0


def test_compute_post_roi_ignores_receipts_without_post_id() -> None:
    """Run-level receipts (no platform/post_id) belong to compute_run_roi."""
    receipts = [
        _r("run-1", 0.10),  # no platform / post_id
        _r("run-1", 0.05, platform="x"),  # platform present but no post_id
        _r("run-1", 0.05, platform="x", post_id="42", account_handle="@me"),
    ]

    report = compute_post_roi(receipts, outcomes_by_post={})

    assert len(report.posts) == 1
    assert report.posts[0].post_key == "x:42"
    assert report.posts[0].cost_usd == 0.05


def test_post_roi_report_totals() -> None:
    report = PostRoiReport(
        posts=[
            PostRoi(
                post_key="x:1",
                platform="x",
                account_handle="@a",
                cost_usd=0.2,
                revenue_usd=10.0,
            ),
            PostRoi(
                post_key="x:2",
                platform="x",
                account_handle="@a",
                cost_usd=0.3,
                revenue_usd=5.0,
            ),
        ]
    )
    assert report.total_cost == 0.5
    assert report.total_revenue == 15.0
    assert report.net_usd == 14.5


def test_build_post_outcomes_index_filters_run_level_keys() -> None:
    """Keys without ``:`` are run-level outcomes — handled by build_outcomes_index."""

    @dataclass
    class _Entry:
        key: str
        content: str
        sources: list[str] = field(default_factory=list)

    class _Memory:
        def __init__(self, entries: list[_Entry]) -> None:
            self._entries = entries

        def recall(self, *, kind: Any, limit: int = 500) -> list[_Entry]:
            return list(self._entries)

    mem = _Memory(
        [
            _Entry("run-only-key", "revenue=42"),  # ignored (no ':')
            _Entry(
                "instagram:ABC",
                "revenue=412.5",
                sources=["https://shop.example/o/1"],
            ),
        ]
    )

    idx = build_post_outcomes_index(mem)

    assert "run-only-key" not in idx
    assert idx["instagram:ABC"]["platform"] == "instagram"
    assert idx["instagram:ABC"]["revenue_usd"] == 412.5
    assert idx["instagram:ABC"]["sources"] == ["https://shop.example/o/1"]


def test_build_post_outcomes_index_handles_no_memory() -> None:
    assert build_post_outcomes_index(None) == {}
