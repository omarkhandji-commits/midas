"""Runtime assembler — compose the core pieces into a ready-to-use app.

Loads config, then wires the budget fuse, the receipts ledger, the Sentinel, and a
budgeted+receipted router. Shared by every channel (CLI, Telegram, dashboard) so they
all enforce the same caps, audit trail, and security gate.

The signing key lives in `<base>/.midas/signing.key` (created on first run) so receipts
verify across runs without depending on an OS keychain backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from midas.core.budget import BudgetFuse, Caps, SpendStore
from midas.core.config.loader import AppConfig, load_app_config
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.router import LLMRouter
from midas.core.sentinel import Sentinel


def _load_or_create_file_signer(base: Path) -> Signer:
    key_path = base / ".midas" / "signing.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return Signer.from_hex_seed(key_path.read_text(encoding="utf-8").strip())
    signer = Signer.generate()
    key_path.write_text(signer.seed_hex(), encoding="utf-8")
    return signer


@dataclass
class Runtime:
    config: AppConfig
    fuse: BudgetFuse
    ledger: ReceiptLedger
    sentinel: Sentinel
    router: LLMRouter

    @property
    def has_providers(self) -> bool:
        return bool(self.config.providers.roles)


def build_runtime(base_dir: str | Path) -> Runtime:
    base = Path(base_dir)
    config = load_app_config(base)

    per_task, daily, monthly = config.caps()
    store = SpendStore(base / ".midas" / "spend.db")
    fuse = BudgetFuse(store, Caps(per_task=per_task, daily=daily, monthly=monthly))

    signer = _load_or_create_file_signer(base)
    ledger = ReceiptLedger(base / ".midas" / "receipts.jsonl", signer)

    sentinel = Sentinel(config.policy)
    # complete_fn defaults to LiteLLM (lazy import) — uses the keys in .env.
    router = LLMRouter(config.providers, fuse=fuse, ledger=ledger)

    return Runtime(config=config, fuse=fuse, ledger=ledger, sentinel=sentinel, router=router)
