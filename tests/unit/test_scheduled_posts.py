"""ScheduledPostStore — add/list/due/cancel + ISO timezone enforcement."""

from __future__ import annotations

import pytest

from midas.flagship.scheduled_posts import ScheduledPostStore


def _store(tmp_path):
    return ScheduledPostStore(tmp_path / "scheduled_posts.json")


def test_add_and_list_roundtrip(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x",
        account_handle="@me",
        text="hello",
        scheduled_at_iso="2026-06-20T09:00:00+00:00",
    )
    assert post.id
    assert post.status == "pending"
    rows = store.list_all()
    assert len(rows) == 1
    assert rows[0].text == "hello"


def test_list_filters_by_window(tmp_path):
    store = _store(tmp_path)
    store.add(
        platform="x", account_handle="@me", text="A",
        scheduled_at_iso="2026-06-20T09:00:00+00:00",
    )
    store.add(
        platform="x", account_handle="@me", text="B",
        scheduled_at_iso="2026-06-25T09:00:00+00:00",
    )
    rows = store.list_all(
        start_iso="2026-06-22T00:00:00+00:00",
        end_iso="2026-06-30T00:00:00+00:00",
    )
    assert [r.text for r in rows] == ["B"]


def test_due_returns_pending_before_now(tmp_path):
    store = _store(tmp_path)
    store.add(
        platform="x", account_handle="@me", text="past",
        scheduled_at_iso="2026-01-01T00:00:00+00:00",
    )
    store.add(
        platform="x", account_handle="@me", text="future",
        scheduled_at_iso="2099-01-01T00:00:00+00:00",
    )
    due = store.due(now_iso="2026-06-17T00:00:00+00:00")
    assert [r.text for r in due] == ["past"]


def test_cancel_transitions_status(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x", account_handle="@me", text="hi",
        scheduled_at_iso="2026-06-20T09:00:00+00:00",
    )
    cancelled = store.cancel(post.id, reason="user changed mind")
    assert cancelled.status == "cancelled"
    assert cancelled.note == "user changed mind"


def test_cannot_remark_non_pending(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x", account_handle="@me", text="hi",
        scheduled_at_iso="2026-06-20T09:00:00+00:00",
    )
    store.mark(post.id, status="published", note="receipt-abc")
    with pytest.raises(ValueError, match="cannot re-mark"):
        store.mark(post.id, status="failed", note="oops")


def test_refuses_naive_timestamp(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="must include a timezone"):
        store.add(
            platform="x", account_handle="@me", text="hi",
            scheduled_at_iso="2026-06-20T09:00:00",
        )


def test_refuses_empty_fields(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="non-empty text"):
        store.add(
            platform="x", account_handle="@me", text="   ",
            scheduled_at_iso="2026-06-20T09:00:00+00:00",
        )
    with pytest.raises(ValueError, match="account_handle"):
        store.add(
            platform="x", account_handle="", text="ok",
            scheduled_at_iso="2026-06-20T09:00:00+00:00",
        )


def test_get_returns_none_for_unknown(tmp_path):
    assert _store(tmp_path).get("missing") is None


def test_persistence_across_instances(tmp_path):
    s1 = _store(tmp_path)
    s1.add(
        platform="x", account_handle="@me", text="persisted",
        scheduled_at_iso="2026-06-20T09:00:00+00:00",
    )
    s2 = _store(tmp_path)
    assert len(s2.list_all()) == 1


def test_z_suffix_accepted(tmp_path):
    store = _store(tmp_path)
    post = store.add(
        platform="x", account_handle="@me", text="ok",
        scheduled_at_iso="2026-06-20T09:00:00Z",
    )
    assert post.scheduled_at_iso.endswith("+00:00")
