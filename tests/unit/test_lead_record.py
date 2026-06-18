"""lead.record — classify, dedup, MemoryKind.RESULT writes."""

from __future__ import annotations

import pytest

from midas.core.memory import MemoryKind, MemoryStore
from midas.flagship.agent.tools.lead import (
    LeadRecordError,
    record_leads,
)


def _msg(**overrides) -> dict:
    base = {
        "uid": "1",
        "from_addr": "prospect@example.com",
        "from_name": "Pat Prospect",
        "subject": "Hello",
        "snippet": "Just saying hi.",
        "date_iso": "2026-06-17T10:00:00+00:00",
        "has_attachment": False,
    }
    base.update(overrides)
    return base


def test_records_lead_when_intent_word_present(tmp_path):
    db = tmp_path / "m.db"
    res = record_leads(
        messages=[_msg(subject="Interested in your service")],
        store_path=db,
    )
    assert len(res.recorded) == 1
    assert res.recorded[0].matched_keyword == "interested"
    store = MemoryStore(db)
    rows = store.recall(kind=MemoryKind.RESULT)
    assert len(rows) == 1
    assert "lead" in rows[0].tags and "cash-signal" in rows[0].tags


def test_skips_message_without_intent(tmp_path):
    res = record_leads(
        messages=[_msg(subject="Newsletter #42", snippet="Weekly digest")],
        store_path=tmp_path / "m.db",
    )
    assert res.recorded == []
    assert res.skipped_not_lead == 1


def test_idempotent_on_same_uid(tmp_path):
    db = tmp_path / "m.db"
    payload = [_msg(subject="Demo request please")]
    record_leads(messages=payload, store_path=db)
    res2 = record_leads(messages=payload, store_path=db)
    assert res2.recorded == []
    assert res2.skipped_existing == 1


def test_skips_malformed_message(tmp_path):
    res = record_leads(
        messages=[{"subject": "no uid or from"}],
        store_path=tmp_path / "m.db",
    )
    assert res.skipped_malformed == 1


def test_refuses_non_list_input(tmp_path):
    with pytest.raises(LeadRecordError, match="must be a list"):
        record_leads(messages="not a list", store_path=tmp_path / "m.db")  # type: ignore[arg-type]


def test_refuses_oversized_batch(tmp_path):
    too_many = [_msg(uid=str(i)) for i in range(101)]
    with pytest.raises(LeadRecordError, match="refusing to record"):
        record_leads(messages=too_many, store_path=tmp_path / "m.db")


def test_matches_keyword_in_snippet(tmp_path):
    res = record_leads(
        messages=[_msg(subject="Hi", snippet="Can you send me your pricing?")],
        store_path=tmp_path / "m.db",
    )
    assert len(res.recorded) == 1
    assert res.recorded[0].matched_keyword == "pricing"


def test_proof_level_low_no_sources_required(tmp_path):
    db = tmp_path / "m.db"
    record_leads(
        messages=[_msg(subject="quote request")],
        store_path=db,
    )
    store = MemoryStore(db)
    rows = store.recall(kind=MemoryKind.RESULT)
    assert rows[0].sources == []
