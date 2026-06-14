"""Typed config models — the machine-readable form of policy.yml / providers.yml / .env."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Autonomy(str, Enum):
    PROPOSE_ONLY = "propose-only"
    SEMI_AUTO = "semi-auto"
    FULL_AUTO_GUARDED = "full-auto-guarded"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── policy.yml ──────────────────────────────────────────────────────────────
class SpendCaps(BaseModel):
    per_task: float = 0.25
    daily: float = 2.0
    monthly: float = 30.0
    on_breach: str = "halt_and_alert"


class ModelsPolicy(BaseModel):
    default: str = "cheap"
    escalate_to_smart_when: list[str] = []


class ActionsPolicy(BaseModel):
    allowed_without_approval: set[str] = set()
    requires_approval: set[str] = set()
    never: set[str] = set()


class ApprovalPolicy(BaseModel):
    source_of_truth: str = "owner_only"
    channels: list[str] = ["telegram", "desktop", "cli"]
    reject_on_timeout: bool = True
    ignore_chat_text_claiming_authority: bool = True


class FilesystemPolicy(BaseModel):
    workspace_only: bool = True
    deny_paths: list[str] = []


class AuditPolicy(BaseModel):
    enabled: bool = True
    path: str = "audit/"
    format: str = "jsonl"
    hash_chained: bool = True
    log: list[str] = []


class SourcesPolicy(BaseModel):
    cite_or_abstain: bool = True
    min_confidence_for_action: Confidence = Confidence.MEDIUM
    self_check_high_stakes: bool = True


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    autonomy: Autonomy = Autonomy.SEMI_AUTO  # approval-default; full-auto is opt-in
    kill_switch: bool = False
    spend_caps: SpendCaps = SpendCaps()
    models: ModelsPolicy = ModelsPolicy()
    actions: ActionsPolicy = ActionsPolicy()
    approval: ApprovalPolicy = ApprovalPolicy()
    egress_allowlist: list[str] = []
    filesystem: FilesystemPolicy = FilesystemPolicy()
    audit: AuditPolicy = AuditPolicy()
    sources: SourcesPolicy = SourcesPolicy()


# ── providers.yml ───────────────────────────────────────────────────────────
class RoleConfig(BaseModel):
    primary: str
    fallbacks: list[str] = []


class ProviderEntry(BaseModel):
    api_key_env: Optional[str] = None
    base_url_env: Optional[str] = None


class RoutingPolicy(BaseModel):
    default_role: str = "cheap"
    escalate_to_smart: list[str] = []
    retry_on_failure: bool = True
    max_retries: int = 2
    enforce_spend_caps: bool = True


class ProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roles: dict[str, RoleConfig] = {}
    providers: dict[str, ProviderEntry] = {}
    routing: RoutingPolicy = RoutingPolicy()


# ── .env ────────────────────────────────────────────────────────────────────
class Settings(BaseSettings):
    """Runtime settings + secrets from environment / .env (field name == env var)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    midas_autonomy: Optional[str] = None
    midas_kill_switch: bool = False
    midas_per_task_spend_cap: Optional[float] = None
    midas_daily_spend_cap: Optional[float] = None
    midas_monthly_spend_cap: Optional[float] = None
    midas_model_cheap: Optional[str] = None
    midas_model_smart: Optional[str] = None

    telegram_bot_token: Optional[str] = None
    telegram_owner_chat_id: Optional[str] = None

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    together_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
