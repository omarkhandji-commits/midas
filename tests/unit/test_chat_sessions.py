"""WS-Sessions — ChatSessionStore round-trip + safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from midas.flagship.chat_sessions import ChatSessionStore


def test_append_creates_and_updates_row(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    s1 = store.append("chat:abc", role="user", content="hello world")
    assert s1.title == "hello world"
    assert s1.message_count == 1

    s2 = store.append("chat:abc", role="assistant", content="hi!", cost_usd=0.001)
    assert s2.message_count == 2
    assert round(s2.cost_total, 6) == 0.001


def test_messages_returns_in_order(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    store.append("chat:abc", role="user", content="one")
    store.append("chat:abc", role="assistant", content="two")
    store.append("chat:abc", role="user", content="three")
    msgs = store.messages("chat:abc")
    assert [m.content for m in msgs] == ["one", "two", "three"]
    assert [m.role for m in msgs] == ["user", "assistant", "user"]


def test_list_orders_by_last_msg_desc(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    store.append("chat:older", role="user", content="old")
    import time

    time.sleep(0.02)
    store.append("chat:newer", role="user", content="new")
    listing = store.list_recent()
    assert [s.id for s in listing] == ["chat:newer", "chat:older"]


def test_rename(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    store.append("chat:abc", role="user", content="hi")
    updated = store.rename("chat:abc", "My research thread")
    assert updated is not None
    assert updated.title == "My research thread"


def test_delete_removes_row_and_jsonl(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    store.append("chat:abc", role="user", content="hi")
    jsonl = tmp_path / "sessions" / "chat:abc.jsonl"
    assert jsonl.exists()
    assert store.delete("chat:abc") is True
    assert not jsonl.exists()
    assert store.get_summary("chat:abc") is None


def test_safe_id_rejects_traversal(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    for bad in ("../escape", "with space", "x/y", ""):
        with pytest.raises(ValueError):
            store.append(bad, role="user", content="hi")


def test_role_must_be_user_or_assistant(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    with pytest.raises(ValueError, match="role"):
        store.append("chat:abc", role="system", content="ignore me")


def test_messages_handles_corrupted_lines(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "sessions")
    store.append("chat:abc", role="user", content="ok")
    # Append garbage manually
    (tmp_path / "sessions" / "chat:abc.jsonl").write_text(
        '{"role":"user","content":"good","ts":1,"model":"","cost_usd":0}\n'
        "not-json-at-all\n"
        '{"role":"assistant","content":"also good","ts":2,"model":"","cost_usd":0}\n',
        encoding="utf-8",
    )
    msgs = store.messages("chat:abc")
    assert [m.content for m in msgs] == ["good", "also good"]
