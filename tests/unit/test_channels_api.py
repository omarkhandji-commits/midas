"""Dashboard channel setup and Telegram listener bridge."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.receipts import ReceiptLedger, Signer
from midas.flagship.channel_settings import (
    ChannelManager,
    DiscordInteractionHandler,
    SlackActionHandler,
    TelegramLongPollListener,
)
from midas.flagship.channels import DiscordConfig, SlackConfig, TelegramConfig
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE
from midas.flagship.provider_settings import MemorySecretVault


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("78" * 32))
    deps = DashboardDeps(
        queue=ApprovalQueue(tmp_path / "apv.db", ledger=ledger),
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        channels=ChannelManager(MemorySecretVault()),
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token, ledger


def _sign_in(client: TestClient, token: LoginToken) -> str:
    r = client.post(
        "/login",
        data={"token": token.value},
        headers={"origin": "http://testserver", "x-midas-csrf": "boot"},
        cookies={"midas_csrf": "boot"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return r.cookies[CSRF_COOKIE]


def test_channels_api_stores_telegram_without_echoing_token(tmp_path: Path) -> None:
    client, token, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)
    headers = {"origin": "http://testserver", "x-midas-csrf": csrf}
    secret = "telegram-token-never-echoed"

    r = client.post(
        "/api/channels/telegram",
        headers=headers,
        json={"bot_token": secret, "owner_chat_id": "42"},
    )

    assert r.status_code == 200
    assert secret not in r.text
    assert r.json()["channel"]["connected"] is True
    listed = client.get("/api/channels")
    assert listed.status_code == 200
    assert secret not in listed.text
    assert client.post("/api/channels/telegram/test", headers=headers).json()["ok"] is True
    receipts_json = "\n".join(receipt.model_dump_json() for receipt in ledger)
    assert "channels.telegram.connect" in receipts_json
    assert secret not in receipts_json

    removed = client.request("DELETE", "/api/channels/telegram", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["channel"]["connected"] is False


def test_channels_api_stores_discord_and_slack_without_echoing_tokens(tmp_path: Path) -> None:
    client, token, _ledger = _client(tmp_path)
    csrf = _sign_in(client, token)
    headers = {"origin": "http://testserver", "x-midas-csrf": csrf}
    discord_secret = "discord-token-never-echoed"
    slack_secret = "slack-token-never-echoed"

    discord = client.post(
        "/api/channels/discord",
        headers=headers,
        json={"bot_token": discord_secret, "owner_user_id": "u1", "guild_id": "g1"},
    )
    slack = client.post(
        "/api/channels/slack",
        headers=headers,
        json={"bot_token": slack_secret, "owner_user_id": "u2", "signing_secret": "sig"},
    )

    assert discord.status_code == 200
    assert slack.status_code == 200
    listed = client.get("/api/channels").text
    assert discord_secret not in listed
    assert slack_secret not in listed
    assert client.post("/api/channels/discord/test", headers=headers).json()["ok"] is True
    assert client.post("/api/channels/slack/test", headers=headers).json()["ok"] is True


def test_telegram_listener_delegates_callbacks_to_shared_queue(tmp_path: Path) -> None:
    queue = ApprovalQueue(tmp_path / "apv.db")
    req = queue.enqueue(run_id="r", agent="a", tool="email", action="send_email", summary="x")
    listener = TelegramLongPollListener(
        config=TelegramConfig.make(bot_token="token", owner_chat_id="42"),
        queue=queue,
    )

    reply = listener._handle_update(
        {"callback_query": {"from": {"id": 42}, "data": f"apv:approve:{req.id}"}}
    )

    assert "approved" in reply
    assert queue.get(req.id).status.value == "approved"


def test_discord_and_slack_handlers_delegate_callbacks_to_shared_queue(tmp_path: Path) -> None:
    queue = ApprovalQueue(tmp_path / "apv.db")
    discord_req = queue.enqueue(
        run_id="r", agent="a", tool="email", action="send_email", summary="discord"
    )
    slack_req = queue.enqueue(
        run_id="r", agent="a", tool="email", action="send_email", summary="slack"
    )
    discord = DiscordInteractionHandler(
        config=DiscordConfig.make(bot_token="token", owner_user_id="u1"),
        queue=queue,
    )
    slack = SlackActionHandler(
        config=SlackConfig.make(bot_token="token", owner_user_id="u2"),
        queue=queue,
    )

    discord_reply = discord.handle_interaction(
        {
            "member": {"user": {"id": "u1"}},
            "data": {"custom_id": f"apv:approve:{discord_req.id}"},
        }
    )
    slack_reply = slack.handle_action(
        {"user": {"id": "u2"}, "actions": [{"action_id": f"apv:reject:{slack_req.id}"}]}
    )

    assert "approved" in discord_reply
    assert "rejected" in slack_reply
    assert queue.get(discord_req.id).status.value == "approved"
    assert queue.get(slack_req.id).status.value == "rejected"
