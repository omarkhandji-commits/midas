"""Load + validate config from policy.yml / providers.yml / .env (fail-fast)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import Autonomy, PolicyConfig, ProvidersConfig, Settings


def load_policy(path: str | Path) -> PolicyConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return PolicyConfig.model_validate(data)


def load_providers(path: str | Path) -> ProvidersConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ProvidersConfig.model_validate(data)


@dataclass
class AppConfig:
    policy: PolicyConfig
    providers: ProvidersConfig
    settings: Settings
    base_dir: Path

    @property
    def kill_switch(self) -> bool:
        return self.policy.kill_switch or self.settings.midas_kill_switch

    @property
    def autonomy(self) -> Autonomy:
        if self.settings.midas_autonomy:
            return Autonomy(self.settings.midas_autonomy)
        return self.policy.autonomy

    def caps(self) -> tuple[float, float, float]:
        """Effective (per_task, daily, monthly) caps — env overrides policy.yml."""
        s, p = self.settings, self.policy.spend_caps
        return (
            s.midas_per_task_spend_cap if s.midas_per_task_spend_cap is not None else p.per_task,
            s.midas_daily_spend_cap if s.midas_daily_spend_cap is not None else p.daily,
            s.midas_monthly_spend_cap if s.midas_monthly_spend_cap is not None else p.monthly,
        )


def load_app_config(base_dir: str | Path) -> AppConfig:
    base = Path(base_dir)
    policy = load_policy(base / "config" / "policy.yml")

    providers_path = base / "config" / "providers.yml"
    if not providers_path.exists():
        providers_path = base / "config" / "providers.example.yml"
    providers = load_providers(providers_path)

    env_file = base / ".env"
    settings = Settings(_env_file=str(env_file) if env_file.exists() else None)  # type: ignore[call-arg]

    return AppConfig(policy=policy, providers=providers, settings=settings, base_dir=base)
