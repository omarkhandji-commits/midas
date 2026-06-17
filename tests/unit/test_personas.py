"""Persona presets — pure-data smoke tests + endpoint check."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.config.models import ActionsPolicy, PolicyConfig, SpendCaps
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.sentinel.gate import Sentinel
from midas.flagship.agent import FsGuard
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.personas import find_persona, list_personas


def test_presets_have_required_fields() -> None:
    for p in list_personas():
        assert p.id
        assert p.label
        assert p.tagline
        assert p.first_action.strip()
        assert isinstance(p.recommended_skills, list)
        assert p.default_currency in {"USD", "EUR", "CAD", "GBP", "JPY"}


def test_persona_ids_are_unique() -> None:
    ids = [p.id for p in list_personas()]
    assert len(ids) == len(set(ids))


def test_find_persona_returns_match() -> None:
    p = find_persona("freelance_dev")
    assert p is not None
    assert p.label == "Freelance developer"


def test_find_persona_returns_none_on_unknown() -> None:
    assert find_persona("astronaut") is None


def _policy() -> PolicyConfig:
    return PolicyConfig(
        spend_caps=SpendCaps(per_task=0.25, daily=2.0, monthly=30.0),
        actions=ActionsPolicy(
            allowed_without_approval={"read_local_files"},
            requires_approval={"repo_write"},
            never={"spam"},
        ),
    )


def test_personas_endpoint_returns_presets(tmp_path: Path) -> None:
    token = LoginToken()
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("12" * 32))
    policy = _policy()
    deps = DashboardDeps(
        queue=ApprovalQueue(tmp_path / "apv.db"),
        sessions=Sessions(SessionConfig(owner_id="o", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        sentinel=Sentinel(policy),
        fs_guard=FsGuard.from_policy(tmp_path, policy.filesystem),
    )
    client = TestClient(create_app(deps), base_url="http://testserver")

    # Unauthenticated → 401
    assert client.get("/api/personas").status_code == 401

    # Sign in via magic link
    r = client.get(f"/login?token={token.value}", follow_redirects=False)
    assert r.status_code == 303

    r = client.get("/api/personas")
    assert r.status_code == 200
    body = r.json()
    ids = {p["id"] for p in body["personas"]}
    assert "freelance_dev" in ids
    assert "content_creator" in ids
