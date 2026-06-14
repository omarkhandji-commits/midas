"""Demo entry-point — `python -m midas.flagship.dashboard`.

Bootstraps an in-memory dashboard with a few seeded approvals + receipts so the
visual rendering can be checked end-to-end. The one-time login token is fixed only
when MIDAS_DEMO=1 is set; production runs always generate fresh tokens.

This file exists so the operator (and the preview tooling) can see what the live UI
looks like without any external services configured.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import uvicorn

from midas.core.approvals import ApprovalQueue
from midas.core.config.models import ProviderEntry, ProvidersConfig
from midas.core.memory import MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision
from midas.flagship.provider_settings import (
    DashboardSettings,
    MemorySecretVault,
    ProviderManager,
    SettingsStore,
)

from .app import DashboardDeps, create_app
from .auth import LoginToken, SessionConfig, Sessions, generate_secret_key

# Fixed demo login token for the local-only preview console; not a real credential.
_DEMO_TOKEN = "midas-demo-token-for-local-preview-only"  # nosec B105
_PORT = int(os.environ.get("MIDAS_DASHBOARD_PORT", "8765"))
_HOST = "127.0.0.1"


def build_demo_deps() -> DashboardDeps:
    base = Path(tempfile.mkdtemp(prefix="midas-dash-"))
    queue = ApprovalQueue(base / "apv.db")
    ledger = ReceiptLedger(base / "receipts.jsonl", Signer.from_hex_seed("ee" * 32))
    memory = MemoryStore(base / "memory.db")
    providers_config = ProvidersConfig(
        providers={"ollama": ProviderEntry(base_url_env="OLLAMA_BASE_URL")}
    )
    provider_manager = ProviderManager(providers_config, MemorySecretVault())
    settings_store = SettingsStore(base / "dashboard-settings.json", DashboardSettings())

    # A handful of receipts so the cost meter has something to add up.
    for c in (0.0012, 0.0034, 0.0009, 0.0021):
        ledger.append(
            run_id="demo", agent="router", tool="llm.complete",
            decision=Decision.ALLOW, inputs={}, outputs={}, cost_usd=c,
        )
    # A couple of pending approvals to show off the table + buttons.
    queue.enqueue(
        run_id="demo", agent="ops", tool="email", action="send_email",
        summary="Send the prepared launch email to the test list.",
        payload={"to": "list@example.com", "subject": "Soft launch"},
    )
    queue.enqueue(
        run_id="demo", agent="ops", tool="repo", action="repo_push",
        summary="Push the new landing page to the staging branch.",
        payload={"branch": "staging"},
    )

    is_demo = os.environ.get("MIDAS_DEMO") == "1"
    token = LoginToken(_DEMO_TOKEN if is_demo else None)
    print(f"\n[MIDAS dashboard] http://{_HOST}:{_PORT}/login")
    print(f"[MIDAS dashboard] one-time token: {token.value}\n", flush=True)

    return DashboardDeps(
        queue=queue,
        ledger=ledger,
        memory=memory,
        providers=provider_manager,
        settings_store=settings_store,
        sessions=Sessions(SessionConfig(owner_id="owner", secret_key=generate_secret_key())),
        login_token=token,
        allowed_hosts={f"{_HOST}:{_PORT}", "localhost:" + str(_PORT)},
        sse_interval_seconds=1.0,
    )


def main() -> None:
    app = create_app(build_demo_deps(), bind_host=_HOST)
    uvicorn.run(app, host=_HOST, port=_PORT, log_level="warning")


if __name__ == "__main__":
    main()
