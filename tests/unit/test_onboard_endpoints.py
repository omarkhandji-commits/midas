"""Onboard endpoints — the /start wizard reads these to drive its 4 steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.config.models import ProvidersConfig
from midas.core.receipts import ReceiptLedger, Signer
from midas.flagship.channel_settings import ChannelManager
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


def _client(tmp_path: Path) -> tuple[TestClient, LoginToken]:
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
        channels=ChannelManager(MemorySecretVault()),
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token


def _sign_in(client: TestClient) -> None:
    # Magic link path — drops session + CSRF cookies. We do not need the CSRF
    # token for GETs, so this is sufficient for the read-only endpoints.
    r = client.get(f"/login?token={client.app.dependency_overrides or ''}")  # noqa: F841
    # Easier path: use the magic GET with the real token.


def _sign_in_with(client: TestClient, token: LoginToken) -> None:
    r = client.get(f"/login?token={token.value}", follow_redirects=False)
    assert r.status_code == 303


def test_detect_ollama_returns_models_or_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _client(tmp_path)
    _sign_in_with(client, token)

    # Ollama HS → must NOT crash, must return empty list.
    monkeypatch.setattr("midas.flagship.onboard.detect_ollama", lambda *a, **k: [])
    r = client.get("/api/onboard/detect-ollama")
    assert r.status_code == 200
    assert r.json() == {"models": [], "chosen": None}


def test_detect_ollama_picks_preferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, token = _client(tmp_path)
    _sign_in_with(client, token)

    monkeypatch.setattr(
        "midas.flagship.onboard.detect_ollama",
        lambda *a, **k: ["codellama:70b", "llama3.1:8b"],
    )
    r = client.get("/api/onboard/detect-ollama")
    assert r.status_code == 200
    body = r.json()
    assert body["models"] == ["codellama:70b", "llama3.1:8b"]
    assert body["chosen"] == "llama3.1:8b"  # small general model preferred


def test_onboard_state_returns_three_flags(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    _sign_in_with(client, token)

    r = client.get("/api/onboard/state")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"has_provider", "has_channel", "has_first_run"}
    # Ollama in catalog is locally usable → has_provider is True out of the box.
    # The wizard treats this as "step 1 done; you can use the local model".
    assert isinstance(body["has_provider"], bool)
    assert body["has_channel"] is False
    assert body["has_first_run"] is False


def test_onboard_state_after_cloud_provider_added(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    _sign_in_with(client, token)
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf
    headers: dict[str, Any] = {"origin": "http://testserver", "x-midas-csrf": csrf}

    add = client.post(
        "/api/providers",
        headers=headers,
        json={"provider": "openai", "api_key": "sk-test"},
    )
    assert add.status_code == 200
    r = client.get("/api/onboard/state")
    assert r.json()["has_provider"] is True


def test_onboard_requires_session(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    # No sign-in.
    r1 = client.get("/api/onboard/detect-ollama")
    r2 = client.get("/api/onboard/state")
    assert r1.status_code == 401
    assert r2.status_code == 401
