"""Dashboard provider/settings API: keychain-backed, sanitized, owner-gated."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.config.models import ProvidersConfig
from midas.core.receipts import ReceiptLedger, Signer
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE
from midas.flagship.provider_settings import (
    DashboardSettings,
    MemorySecretVault,
    ProviderManager,
    SettingsStore,
)


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken, ReceiptLedger]:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("12" * 32))
    deps = DashboardDeps(
        queue=ApprovalQueue(tmp_path / "apv.db"),
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        providers=ProviderManager(ProvidersConfig(), MemorySecretVault(), env={}),
        settings_store=SettingsStore(tmp_path / "settings.json", DashboardSettings()),
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


def test_provider_key_is_stored_but_never_echoed(tmp_path: Path) -> None:
    client, token, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)
    headers = {"origin": "http://testserver", "x-midas-csrf": csrf}
    secret = "test-secret-value-never-echoed"

    add = client.post(
        "/api/providers",
        headers=headers,
        json={"provider": "openai", "api_key": secret},
    )
    assert add.status_code == 200
    assert secret not in add.text
    payload = add.json()["provider"]
    assert payload["name"] == "openai"
    assert payload["configured"] is True
    assert payload["has_api_key"] is True
    assert payload["api_key_env"] == "OPENAI_API_KEY"

    listed = client.get("/api/providers")
    assert listed.status_code == 200
    assert secret not in listed.text
    openai = next(p for p in listed.json()["providers"] if p["name"] == "openai")
    assert openai["configured"] is True

    dry = client.post("/api/providers/test", headers=headers, json={"provider": "openai"})
    assert dry.status_code == 200
    assert dry.json()["ok"] is True
    assert secret not in dry.text
    assert client.post("/api/providers/test", headers=headers, json=[]).status_code == 400

    receipts_json = "\n".join(r.model_dump_json() for r in ledger)
    assert "providers.add" in receipts_json
    assert secret not in receipts_json

    removed = client.request("DELETE", "/api/providers/openai", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["provider"]["configured"] is False
    assert secret not in removed.text


def test_settings_round_trip_and_validation(tmp_path: Path) -> None:
    client, token, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)
    headers = {"origin": "http://testserver", "x-midas-csrf": csrf}

    initial = client.get("/api/settings")
    assert initial.status_code == 200
    assert initial.json()["settings"]["autonomy"] == "semi-auto"

    updated = client.post(
        "/api/settings",
        headers=headers,
        json={
            "per_task_cap": 1.5,
            "daily_cap": 10,
            "monthly_cap": 100,
            "autonomy": "propose-only",
            "theme": "dark",
            "language": "fr",
        },
    )
    assert updated.status_code == 200
    settings = updated.json()["settings"]
    assert settings["per_task_cap"] == 1.5
    assert settings["autonomy"] == "propose-only"
    assert settings["language"] == "fr"
    assert any(r.body.tool == "settings.update" for r in ledger)

    bad = client.post("/api/settings", headers=headers, json={"daily_cap": -1})
    assert bad.status_code == 400
    assert client.post("/api/settings", headers=headers, json=[]).status_code == 400
