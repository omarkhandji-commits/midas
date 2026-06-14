"""Runtime assembler for the MIDAS product surface.

Every channel should use this object so memory, approvals, receipts, cache, budget,
source verification, and Market Radar are not separate demo pieces.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from midas.core.approvals import ApprovalQueue
from midas.core.budget import BudgetFuse, Caps, SpendStore
from midas.core.cache import ResearchCache
from midas.core.config.loader import AppConfig, load_app_config
from midas.core.context import ContextBudget, RunMode, SafeContextCompressor
from midas.core.memory import MemoryStore
from midas.core.receipts import ReceiptLedger, Signer
from midas.core.receipts.models import Decision
from midas.core.router import LLMRouter
from midas.core.sentinel import Sentinel
from midas.core.web import (
    CachedFetcher,
    CachedSearchAdapter,
    Fetcher,
    HttpxFetcher,
    SearchAdapter,
    SearxngSearchAdapter,
    SourceVerifier,
    StaticSearchAdapter,
)
from midas.flagship.channel_settings import ChannelManager
from midas.flagship.market import CompetitorStore
from midas.flagship.provider_settings import (
    DashboardSettings,
    KeyringSecretVault,
    ProviderManager,
    SettingsStore,
)


def _load_or_create_file_signer(state: Path) -> Signer:
    key_path = state / "signing.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return Signer.from_hex_seed(key_path.read_text(encoding="utf-8").strip())
    signer = Signer.generate()
    key_path.write_text(signer.seed_hex(), encoding="utf-8")
    return signer


@dataclass
class Runtime:
    base_dir: Path
    state_dir: Path
    config: AppConfig
    fuse: BudgetFuse
    ledger: ReceiptLedger
    sentinel: Sentinel
    router: LLMRouter
    memory: MemoryStore
    approvals: ApprovalQueue
    research_cache: ResearchCache
    search: SearchAdapter
    fetcher: Fetcher
    verifier: SourceVerifier
    competitors: CompetitorStore
    context: SafeContextCompressor
    providers: ProviderManager
    settings_store: SettingsStore
    channels: ChannelManager

    @property
    def has_providers(self) -> bool:
        return bool(self.config.providers.roles)

    def append_receipt(
        self,
        *,
        run_id: str,
        agent: str,
        tool: str,
        inputs: object,
        outputs: object,
        decision: Decision = Decision.ALLOW,
        cost_usd: float = 0.0,
    ) -> None:
        self.ledger.append(
            run_id=run_id,
            agent=agent,
            tool=tool,
            decision=decision,
            inputs=inputs,
            outputs=outputs,
            cost_usd=cost_usd,
        )

    def dashboard_deps(self, *, allowed_host: str = "127.0.0.1:8765") -> Any:
        from midas.flagship.dashboard import (
            DashboardDeps,
            LoginToken,
            SessionConfig,
            Sessions,
            generate_secret_key,
        )

        owner = self.config.settings.telegram_owner_chat_id or "local-owner"
        sessions = Sessions(SessionConfig(owner_id=owner, secret_key=generate_secret_key()))
        return DashboardDeps(
            queue=self.approvals,
            sessions=sessions,
            login_token=LoginToken(),
            allowed_hosts={allowed_host, "localhost:8765", "testserver"},
            ledger=self.ledger,
            memory=self.memory,
            competitors=self.competitors,
            providers=self.providers,
            settings_store=self.settings_store,
            router=self.router,
            sentinel=self.sentinel,
            search=self.search,
            verifier=self.verifier,
            channels=self.channels,
        )


def build_runtime(base_dir: str | Path) -> Runtime:
    base = Path(base_dir)
    state = _state_dir(base)
    config = load_app_config(base)
    providers = ProviderManager(config.providers, KeyringSecretVault())
    providers.apply_to_environment()
    channels = ChannelManager(KeyringSecretVault())

    per_task, daily, monthly = config.caps()
    fuse = BudgetFuse(
        SpendStore(state / "spend.db"),
        Caps(per_task=per_task, daily=daily, monthly=monthly),
    )

    signer = _load_or_create_file_signer(state)
    ledger = ReceiptLedger(state / "receipts.jsonl", signer)
    sentinel = Sentinel(config.policy)
    router = LLMRouter(config.providers, fuse=fuse, ledger=ledger)
    memory = MemoryStore(state / "memory.db")
    approvals = ApprovalQueue(state / "approvals.db", ledger=ledger, owner_ids=_owner_ids(config))
    research_cache = ResearchCache(state / "research.db")
    fetcher = cast(Fetcher, CachedFetcher(HttpxFetcher(), research_cache))
    search = cast(SearchAdapter, _build_search(research_cache))
    verifier = SourceVerifier(fetcher, require_support=True)
    competitors = CompetitorStore(state / "competitors.db")
    context = SafeContextCompressor(ContextBudget.for_mode(_run_mode()))
    settings_store = SettingsStore(
        state / "dashboard-settings.json",
        DashboardSettings.from_config(config),
    )

    return Runtime(
        base_dir=base,
        state_dir=state,
        config=config,
        fuse=fuse,
        ledger=ledger,
        sentinel=sentinel,
        router=router,
        memory=memory,
        approvals=approvals,
        research_cache=research_cache,
        search=search,
        fetcher=fetcher,
        verifier=verifier,
        competitors=competitors,
        context=context,
        providers=providers,
        settings_store=settings_store,
        channels=channels,
    )


def _owner_ids(config: AppConfig) -> set[str]:
    ids: set[str] = {"cli", "dashboard"}
    if config.settings.telegram_owner_chat_id:
        ids.add(config.settings.telegram_owner_chat_id)
    return ids


def _state_dir(base: Path) -> Path:
    override = os.getenv("MIDAS_STATE_DIR", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path

    preferred = base / ".midas"
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        _probe_writable(preferred)
        return preferred
    except (OSError, PermissionError):
        fallback = base / "memory"
        try:
            if fallback.exists():
                _probe_writable(fallback)
                return fallback
            fallback.mkdir(parents=True, exist_ok=True)
            _probe_writable(fallback)
            return fallback
        except (OSError, PermissionError):
            digest = hashlib.sha256(str(base.resolve()).encode("utf-8")).hexdigest()[:12]
            tmp = Path(tempfile.gettempdir()) / "midas-state" / digest
            tmp.mkdir(parents=True, exist_ok=True)
            return tmp


def _probe_writable(path: Path) -> None:
    probe = path / ".write-probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)


def _build_search(cache: ResearchCache) -> SearchAdapter:
    searxng = os.getenv("MIDAS_SEARXNG_URL", "").strip()
    if searxng:
        return CachedSearchAdapter(SearxngSearchAdapter(searxng), cache)
    return StaticSearchAdapter([])


def _run_mode() -> RunMode:
    mode = os.getenv("MIDAS_RUN_MODE", "deep").strip().lower()
    if mode in {"fast", "deep", "war-room"}:
        return cast(RunMode, mode)
    return "deep"
