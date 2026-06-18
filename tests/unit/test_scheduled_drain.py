"""drain_due — enqueues approvals for due posts, no auto-egress."""

from __future__ import annotations

from dataclasses import dataclass, field

from midas.flagship.scheduled_posts import ScheduledPostStore, drain_due


@dataclass
class FakePlan:
    sha256_intent: str = "deadbeef"


@dataclass
class FakeApprovals:
    calls: list[dict] = field(default_factory=list)

    def enqueue(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def _fake_plan_ok(**kwargs):
    return FakePlan(sha256_intent="ok" * 32)


def _fake_plan_fail(**kwargs):
    raise ValueError("media file missing")


def _store(tmp_path):
    return ScheduledPostStore(tmp_path / "sp.json")


def test_drain_enqueues_due_post(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x", account_handle="@me", text="hello",
        scheduled_at_iso="2026-01-01T00:00:00+00:00",
    )
    approvals = FakeApprovals()
    out = drain_due(
        store, approvals=approvals, plan_fn=_fake_plan_ok,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    assert out.enqueued == [post.id]
    assert len(approvals.calls) == 1
    call = approvals.calls[0]
    assert call["tool"] == "social.publish"
    assert call["action"] == "send_social"
    assert call["payload"]["scheduled_post_id"] == post.id
    assert store.get(post.id).status == "queued"


def test_drain_skips_future_posts(tmp_path):
    store = _store(tmp_path)
    store.add(
        platform="x", account_handle="@me", text="future",
        scheduled_at_iso="2099-01-01T00:00:00+00:00",
    )
    approvals = FakeApprovals()
    out = drain_due(
        store, approvals=approvals, plan_fn=_fake_plan_ok,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    assert out.enqueued == []
    assert approvals.calls == []


def test_drain_marks_failed_when_plan_raises(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x", account_handle="@me", text="oops",
        scheduled_at_iso="2026-01-01T00:00:00+00:00",
    )
    approvals = FakeApprovals()
    out = drain_due(
        store, approvals=approvals, plan_fn=_fake_plan_fail,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    assert out.enqueued == []
    assert out.failed == [(post.id, "media file missing")]
    assert store.get(post.id).status == "failed"
    assert approvals.calls == []  # never enqueued


def test_drain_idempotent_post_already_queued_not_repicked(tmp_path):
    store = _store(tmp_path)
    store.add(
        platform="x", account_handle="@me", text="x",
        scheduled_at_iso="2026-01-01T00:00:00+00:00",
    )
    approvals = FakeApprovals()
    drain_due(
        store, approvals=approvals, plan_fn=_fake_plan_ok,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    # Second pass should pick nothing — post is no longer pending.
    out2 = drain_due(
        store, approvals=approvals, plan_fn=_fake_plan_ok,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    assert out2.enqueued == []
    assert len(approvals.calls) == 1


def test_drain_empty_queue_is_noop(tmp_path):
    out = drain_due(
        _store(tmp_path), approvals=FakeApprovals(), plan_fn=_fake_plan_ok,
        now_iso="2026-06-18T00:00:00+00:00",
    )
    assert out.enqueued == []
    assert out.failed == []
