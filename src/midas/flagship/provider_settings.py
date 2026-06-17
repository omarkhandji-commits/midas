"""Dashboard-facing provider vault and local settings store.

This is deliberately a product-layer adapter: core keeps the provider catalog and
router, while the flagship dashboard owns keychain storage, status JSON, and UI
settings persistence.
"""

from __future__ import annotations

import json
import os
from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from midas.core.config.loader import AppConfig
from midas.core.config.models import Autonomy, ProvidersConfig, RoleConfig
from midas.core.providers import ProviderSpec, catalog, diagnose_providers
from midas.core.router import ChatResult, LLMRouter
from midas.flagship.onboard import upsert_env
from midas.flagship.provider_defaults import cheap_model_for

_KEYCHAIN_SERVICE = "midas-agent"
_THEMES = {"system", "light", "dark"}
_LANGUAGES = {"en", "fr"}


class SecretVault(Protocol):
    def get(self, handle: str) -> str | None: ...
    def set(self, handle: str, value: str) -> None: ...
    def delete(self, handle: str) -> None: ...


class KeyringSecretVault:
    """OS keychain vault. Raw values never leave this class except into env vars."""

    def __init__(self, *, service: str = _KEYCHAIN_SERVICE) -> None:
        self.service = service

    def get(self, handle: str) -> str | None:
        import keyring

        return keyring.get_password(self.service, handle)

    def set(self, handle: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service, handle, value)

    def delete(self, handle: str) -> None:
        import keyring

        try:
            keyring.delete_password(self.service, handle)
        except keyring.errors.PasswordDeleteError:
            return


class MemorySecretVault:
    """Test/demo vault with the same no-echo contract as the OS keychain."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, handle: str) -> str | None:
        return self._values.get(handle)

    def set(self, handle: str, value: str) -> None:
        self._values[handle] = value

    def delete(self, handle: str) -> None:
        self._values.pop(handle, None)


@dataclass(frozen=True)
class ProviderTestResult:
    provider: str
    ok: bool
    live: bool
    message: str
    model: str | None = None
    cost_usd: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class ProviderManager:
    """Provider status + keychain writes for dashboard and future onboarding."""

    def __init__(
        self,
        config: ProvidersConfig,
        vault: SecretVault,
        *,
        env: MutableMapping[str, str] | None = None,
        env_path: Path | None = None,
    ) -> None:
        self.config = config
        self.vault = vault
        self.env = env if env is not None else os.environ
        # When set, ``add()`` persists ``MIDAS_MODEL_CHEAP`` to this ``.env`` file
        # the first time a usable key is stored, so the agent works immediately
        # without a restart. Left ``None`` in tests that pass a fresh dict env.
        self.env_path = env_path

    def list_statuses(self) -> list[dict[str, Any]]:
        return [self.status(name) for name in self._provider_names()]

    def status(self, provider: str) -> dict[str, Any]:
        name = _normalise_provider(provider)
        spec = self._spec(name)
        api_key_env, base_url_env = self._handles(name, spec)
        env_view = dict(self.env)
        for handle in (api_key_env, base_url_env):
            if handle and self.vault.get(handle):
                env_view[handle] = "<stored-in-keychain>"
        diagnosed = {s.name: s for s in diagnose_providers(self.config, env=env_view)}
        status = diagnosed.get(name)
        if status is None:
            raise ValueError(f"unknown provider: {name}")
        has_api_key = bool(
            api_key_env and (self.env.get(api_key_env) or self.vault.get(api_key_env))
        )
        has_base_url = bool(
            base_url_env and (self.env.get(base_url_env) or self.vault.get(base_url_env))
        )
        return {
            "name": name,
            "label": spec.label if spec else name.replace("_", " ").title(),
            "configured": status.configured,
            "local": status.local,
            "missing": list(status.missing),
            "api_key_env": api_key_env,
            "base_url_env": base_url_env,
            "has_api_key": has_api_key,
            "has_base_url": has_base_url,
            "notes": status.notes,
            "source": self._source(name, api_key_env, base_url_env),
        }

    def add(
        self,
        provider: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        name = _normalise_provider(provider)
        spec = self._spec(name)
        if spec is None and name not in self.config.providers:
            raise ValueError(f"unknown provider: {name}")
        api_key_env, base_url_env = self._handles(name, spec)

        if api_key and api_key_env:
            self.vault.set(api_key_env, api_key.strip())
        elif api_key and not api_key_env:
            raise ValueError(f"{name} does not accept an API key")
        if base_url and base_url_env:
            self.vault.set(base_url_env, base_url.strip())
        elif base_url and not base_url_env:
            raise ValueError(f"{name} does not accept a base URL")

        self.apply_to_environment()
        if api_key:
            self._wire_cheap_role(name)
        return self.status(name)

    def _wire_cheap_role(self, name: str) -> None:
        """First-time wiring: point the ``cheap`` role at this provider's default.

        Only acts when (1) we know a default model for the provider, (2) no
        explicit ``MIDAS_MODEL_CHEAP`` is already set (env wins over our guess),
        and (3) the current ``cheap`` role is empty or points to a provider that
        is not configured. The router reads ``self.config.roles`` lazily, so the
        in-process mutation takes effect on the next call — no restart needed.
        """
        if self.env.get("MIDAS_MODEL_CHEAP"):
            return
        model = cheap_model_for(name)
        if not model:
            return
        current = self.config.roles.get("cheap")
        if current and current.primary and self._role_is_satisfied(current.primary):
            return
        self.config.roles["cheap"] = RoleConfig(
            primary=model,
            fallbacks=current.fallbacks if current else [],
        )
        self.env["MIDAS_MODEL_CHEAP"] = model
        if self.env_path is not None:
            upsert_env(self.env_path, {"MIDAS_MODEL_CHEAP": model})

    def _role_is_satisfied(self, model_id: str) -> bool:
        """A ``provider/model`` id is satisfied if that provider is configured.

        Used by ``_wire_cheap_role`` so we never overwrite a role that already
        points to a working provider (respect prior operator decisions).
        """
        if "/" not in model_id:
            return False
        provider, _ = model_id.split("/", 1)
        try:
            status = self.status(provider)
        except ValueError:
            return False
        return bool(status.get("configured"))

    def remove(self, provider: str) -> dict[str, Any]:
        name = _normalise_provider(provider)
        spec = self._spec(name)
        if spec is None and name not in self.config.providers:
            raise ValueError(f"unknown provider: {name}")
        api_key_env, base_url_env = self._handles(name, spec)
        for handle in (api_key_env, base_url_env):
            if handle:
                self.vault.delete(handle)
                self.env.pop(handle, None)
        return self.status(name)

    def test(
        self,
        provider: str,
        *,
        live: bool = False,
        model: str | None = None,
        router: LLMRouter | None = None,
    ) -> ProviderTestResult:
        status = self.status(provider)
        if not status["configured"]:
            missing = ", ".join(status["missing"]) or "provider metadata"
            return ProviderTestResult(
                provider=status["name"],
                ok=False,
                live=live,
                message=f"Missing {missing}.",
            )
        if not live:
            return ProviderTestResult(
                provider=status["name"],
                ok=True,
                live=False,
                message="Dry check passed. Key/base URL is present or the local default is usable.",
            )
        if router is None or not model:
            return ProviderTestResult(
                provider=status["name"],
                ok=False,
                live=True,
                message="Live test requires a model id.",
            )
        self.apply_to_environment()
        result = router.complete_model(
            model,
            [{"role": "user", "content": "Reply with MIDAS_OK only."}],
            task_id=f"provider:test:{status['name']}",
            run_id="provider:test",
            est_usd=0.02,
            agent="provider-manager",
        )
        return ProviderTestResult(
            provider=status["name"],
            ok="MIDAS_OK" in result.text,
            live=True,
            message=result.text.strip(),
            model=result.model,
            cost_usd=float(result.cost_usd or 0.0),
        )

    def apply_to_environment(self) -> None:
        for name in self._provider_names():
            spec = self._spec(name)
            for handle in self._handles(name, spec):
                if not handle:
                    continue
                value = self.vault.get(handle)
                if value:
                    self.env[handle] = value

    def _provider_names(self) -> list[str]:
        return sorted(set(catalog()) | set(self.config.providers))

    def _spec(self, name: str) -> ProviderSpec | None:
        return catalog().get(name)

    def _handles(self, name: str, spec: ProviderSpec | None) -> tuple[str | None, str | None]:
        entry = self.config.providers.get(name)
        api_key_env = entry.api_key_env if entry and entry.api_key_env else (
            spec.api_key_env if spec else None
        )
        base_url_env = entry.base_url_env if entry and entry.base_url_env else (
            spec.base_url_env if spec else None
        )
        return api_key_env, base_url_env

    def _source(self, name: str, api_key_env: str | None, base_url_env: str | None) -> str:
        has_base_url = bool(
            base_url_env and (self.env.get(base_url_env) or self.vault.get(base_url_env))
        )
        if name == "ollama" and not has_base_url:
            return "local-default"
        handles = [h for h in (api_key_env, base_url_env) if h]
        if any(self.vault.get(h) for h in handles):
            return "keychain"
        if any(self.env.get(h) for h in handles):
            return "environment"
        return "missing"


@dataclass(frozen=True)
class DashboardSettings:
    per_task_cap: float = 0.25
    daily_cap: float = 2.0
    monthly_cap: float = 30.0
    autonomy: str = Autonomy.SEMI_AUTO.value
    theme: str = "system"
    language: str = "en"

    @classmethod
    def from_config(cls, config: AppConfig) -> DashboardSettings:
        per_task, daily, monthly = config.caps()
        return cls(
            per_task_cap=per_task,
            daily_cap=daily,
            monthly_cap=monthly,
            autonomy=config.autonomy.value,
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class SettingsStore:
    def __init__(self, path: str | Path, defaults: DashboardSettings) -> None:
        self.path = Path(path)
        self.defaults = defaults
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> DashboardSettings:
        if not self.path.exists():
            return self.defaults
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return _settings_from_dict({**self.defaults.to_json(), **data})

    def update(self, data: dict[str, Any]) -> DashboardSettings:
        current = self.get().to_json()
        for field in (
            "per_task_cap",
            "daily_cap",
            "monthly_cap",
            "autonomy",
            "theme",
            "language",
        ):
            if field in data:
                current[field] = data[field]
        settings = _settings_from_dict(current)
        self.path.write_text(
            json.dumps(settings.to_json(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return settings


def _settings_from_dict(data: dict[str, Any]) -> DashboardSettings:
    autonomy = str(data.get("autonomy", Autonomy.SEMI_AUTO.value))
    if autonomy not in {a.value for a in Autonomy}:
        raise ValueError(f"invalid autonomy: {autonomy}")
    theme = str(data.get("theme", "system"))
    if theme not in _THEMES:
        raise ValueError(f"invalid theme: {theme}")
    language = str(data.get("language", "en"))
    if language not in _LANGUAGES:
        raise ValueError(f"invalid language: {language}")
    per_task = _positive_float(data.get("per_task_cap"), "per_task_cap")
    daily = _positive_float(data.get("daily_cap"), "daily_cap")
    monthly = _positive_float(data.get("monthly_cap"), "monthly_cap")
    return DashboardSettings(
        per_task_cap=per_task,
        daily_cap=daily,
        monthly_cap=monthly,
        autonomy=autonomy,
        theme=theme,
        language=language,
    )


def _positive_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return parsed


def _normalise_provider(provider: str) -> str:
    name = provider.strip().lower().replace("-", "_")
    if not name:
        raise ValueError("provider is required")
    return name


def fake_test_router(config: ProvidersConfig) -> LLMRouter:
    """Small helper for demos/tests that need router-shaped provider checks."""

    return LLMRouter(
        config,
        complete_fn=lambda model, messages: ChatResult(
            text="MIDAS_OK",
            model=model,
            prompt_tokens=sum(len(str(m.get("content", ""))) for m in messages),
            completion_tokens=3,
            cost_usd=0.0,
        ),
    )
