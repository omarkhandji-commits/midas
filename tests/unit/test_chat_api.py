"""Dashboard chat SSE: router + budget + Sentinel + approval queue."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from midas.core.approvals import ApprovalQueue
from midas.core.budget import BudgetFuse, Caps, SpendStore
from midas.core.config.models import PolicyConfig, ProvidersConfig, RoleConfig
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.router import ChatResult, LLMRouter
from midas.core.sentinel import Sentinel
from midas.flagship.dashboard import (
    DashboardDeps,
    LoginToken,
    SessionConfig,
    Sessions,
    create_app,
    generate_secret_key,
)
from midas.flagship.dashboard.app import CSRF_COOKIE


def _client(
    tmp_path: Path,
    *,
    cap: float = 1.0,
    response: str = (
        "Here is the draft.\n"
        'APPROVAL_REQUIRED: {"tool":"email","action":"send_email",'
        '"summary":"Send prepared email","payload":{"draft":"hello"}}'
    ),
) -> tuple[TestClient, LoginToken, ApprovalQueue, list[str], ReceiptLedger]:
    calls: list[str] = []
    providers = ProvidersConfig(roles={"cheap": RoleConfig(primary="local/test")})
    fuse = BudgetFuse(SpendStore(tmp_path / "spend.db"), Caps(per_task=cap, daily=cap, monthly=cap))
    ledger = ReceiptLedger(tmp_path / "r.jsonl", Signer.from_hex_seed("34" * 32))
    router = LLMRouter(
        providers,
        fuse=fuse,
        ledger=ledger,
        complete_fn=lambda model, messages: _complete(model, messages, calls, response),
    )
    queue = ApprovalQueue(tmp_path / "apv.db", ledger=ledger)
    token = LoginToken()
    deps = DashboardDeps(
        queue=queue,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={"testserver"},
        ledger=ledger,
        router=router,
        sentinel=Sentinel(PolicyConfig()),
        chat_est_usd=0.02,
    )
    return TestClient(create_app(deps), base_url="http://testserver"), token, queue, calls, ledger


def _complete(
    model: str,
    messages: list[dict],
    calls: list[str],
    response: str,
) -> ChatResult:
    calls.append(model)
    return ChatResult(
        text=response,
        model=model,
        prompt_tokens=sum(len(str(m.get("content", ""))) for m in messages),
        completion_tokens=12,
        cost_usd=0.001,
    )


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


def test_chat_streams_answer_and_queues_risky_action(tmp_path: Path) -> None:
    client, token, queue, calls, ledger = _client(tmp_path)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/chat",
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
        json={"message": "Draft and send email to the lead."},
    )

    assert r.status_code == 200
    assert "event: start" in r.text
    assert "event: delta" in r.text
    assert "event: approval" in r.text
    assert "event: done" in r.text
    assert calls == ["local/test"]
    pending = queue.pending()
    assert len(pending) == 1
    assert pending[0].action == "send_email"
    assert pending[0].tool == "email"
    assert any(receipt.body.decision.value == "queue_approval" for receipt in ledger)


def test_chat_budget_breach_streams_error_without_model_call(tmp_path: Path) -> None:
    client, token, queue, calls, _ledger = _client(tmp_path, cap=0.001)
    csrf = _sign_in(client, token)

    r = client.post(
        "/api/chat",
        headers={"origin": "http://testserver", "x-midas-csrf": csrf},
        json={"message": "Think deeply."},
    )

    assert r.status_code == 200
    assert "event: error" in r.text
    assert "budget_exceeded" in r.text
    assert calls == []
    assert queue.pending() == []
