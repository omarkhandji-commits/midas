"""WS-Sessions P3b — ```action fenced block extraction in chat replies."""

from __future__ import annotations

from midas.flagship.chat import _extract_action_block


def test_extracts_action_block_and_strips_from_text() -> None:
    reply = (
        "Here's the email draft you asked for:\n\n"
        "Subject: hi\nBody: hello.\n\n"
        "```action\n"
        '{"tool":"email","action":"send_email","summary":"Send the draft",'
        '"payload":{"draft":"Subject: hi\\nBody: hello."}}\n'
        "```"
    )
    visible, action = _extract_action_block(reply)
    assert action is not None
    assert action["tool"] == "email"
    assert action["action"] == "send_email"
    assert action["summary"] == "Send the draft"
    assert "```action" not in visible
    assert "Here's the email draft" in visible


def test_no_action_block_returns_text_untouched() -> None:
    reply = "Just a chat answer, no action needed."
    visible, action = _extract_action_block(reply)
    assert visible == reply
    assert action is None


def test_malformed_json_falls_back_to_none() -> None:
    reply = "ok\n```action\nthis is not json\n```"
    visible, action = _extract_action_block(reply)
    assert action is None
    assert "```action" not in visible


def test_non_dict_payload_rejected() -> None:
    reply = "ok\n```action\n[1,2,3]\n```"
    visible, action = _extract_action_block(reply)
    assert action is None
