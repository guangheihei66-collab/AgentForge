"""Launcher-local provider settings workflow and safe connection results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time

from app.agents.providers.base import LLMProvider, ProviderError
from app.agents.providers.base import LLMResponse
from app.agents.providers.config import ProviderConfig
from app.agents.providers.settings import (
    ProviderSettingsError,
    ProviderSettingsSnapshot,
    ProviderSettingsStore,
    SecureStorageError,
    SUPPORTED_REAL_PROVIDERS,
)


@dataclass(frozen=True, slots=True)
class ProviderSettingsForm:
    provider: str
    base_url: str
    model: str
    api_key: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionTestResult:
    success: bool
    provider: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    failure_category: str | None = None
    message: str = ""


def _build_provider(config: object) -> LLMProvider:
    """Import the transport lazily so the compact launcher stays lightweight."""

    from app.agents.providers.config import build_provider

    return build_provider(config)


_PROVIDER_PROBE = r'''
import json
from app.agents.providers import build_provider, load_provider_config
from app.agents.providers.base import ProviderError

try:
    config = load_provider_config(allow_default_mock=False)
    if config.provider == "mock":
        print(json.dumps({"ok": False, "failure_category": "INVALID_CONFIGURATION"}, separators=(",", ":")))
        raise SystemExit(0)
    response = build_provider(config).test_connection()
    print(json.dumps({
        "ok": True,
        "provider": response.provider,
        "model": response.model,
        "duration_ms": response.duration_ms,
    }, separators=(",", ":")))
except ProviderError as exc:
    print(json.dumps({"ok": False, "failure_category": exc.category.value}, separators=(",", ":")))
except Exception:
    print(json.dumps({"ok": False, "failure_category": "PROVIDER_ERROR"}, separators=(",", ":")))
'''


class SubprocessProviderConnection:
    """Run the existing provider transport under the approved backend venv."""

    def __init__(self, *, python_path: Path, backend_path: Path) -> None:
        self.python_path = Path(python_path)
        self.backend_path = Path(backend_path)

    def __call__(self, config: ProviderConfig) -> ConnectionTestResult:
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONPATH": str(self.backend_path),
                "AGENTFORGE_LLM_PROVIDER": config.provider,
                "AGENTFORGE_LLM_BASE_URL": config.base_url,
                "AGENTFORGE_LLM_MODEL": config.model,
                "AGENTFORGE_LLM_API_KEY": config.api_key,
                "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE": config.structured_output_mode.value,
            }
        )
        options = {
            "capture_output": True,
            "text": True,
            "timeout": max(5.0, config.timeout_seconds + 5.0),
        }
        try:
            from .process_session import hidden_popen_options

            options.update(hidden_popen_options())
            started = time.perf_counter()
            completed = subprocess.run(
                [str(self.python_path), "-c", _PROVIDER_PROBE],
                env=environment,
                **options,
            )
        except subprocess.TimeoutExpired:
            return ConnectionTestResult(
                success=False,
                failure_category="TIMEOUT",
                message="Provider connection timed out",
            )
        except (OSError, subprocess.SubprocessError):
            return ConnectionTestResult(
                success=False,
                failure_category="PROVIDER_RUNTIME_UNAVAILABLE",
                message="Provider runtime is unavailable",
            )
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        try:
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, TypeError, ValueError):
            return ConnectionTestResult(
                success=False,
                failure_category="INVALID_RESPONSE",
                message="Provider returned an invalid response",
                duration_ms=duration_ms,
            )
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return ConnectionTestResult(
                success=False,
                failure_category=str(payload.get("failure_category", "PROVIDER_ERROR"))[:64]
                if isinstance(payload, dict)
                else "PROVIDER_ERROR",
                message="Provider connection failed",
                duration_ms=duration_ms,
            )
        provider = payload.get("provider")
        model = payload.get("model")
        if not isinstance(provider, str) or not isinstance(model, str):
            return ConnectionTestResult(
                success=False,
                failure_category="INVALID_RESPONSE",
                message="Provider returned an invalid response",
                duration_ms=duration_ms,
            )
        return ConnectionTestResult(
            success=True,
            provider=provider,
            model=model,
            duration_ms=payload.get("duration_ms") if isinstance(payload.get("duration_ms"), int) else duration_ms,
            message="Connection successful",
        )


class ProviderSettingsService:
    """Validate, test, and persist candidate settings without workflow access."""

    def __init__(
        self,
        *,
        store: ProviderSettingsStore | None = None,
        provider_builder: Callable[[object], LLMProvider] | None = None,
        connection_runner: Callable[[ProviderConfig], ConnectionTestResult] | None = None,
    ) -> None:
        self.store = store or ProviderSettingsStore()
        self.provider_builder = provider_builder or _build_provider
        self.connection_runner = connection_runner

    def snapshot(self) -> ProviderSettingsSnapshot:
        return self.store.snapshot()

    @staticmethod
    def supported_providers() -> tuple[str, ...]:
        return SUPPORTED_REAL_PROVIDERS

    def test_connection(self, form: ProviderSettingsForm) -> ConnectionTestResult:
        try:
            config = self.store.validate_candidate(
                provider=form.provider,
                base_url=form.base_url,
                model=form.model,
                api_key=form.api_key,
            )
            if self.connection_runner is not None:
                return self.connection_runner(config)
            provider = self.provider_builder(config)
            if provider.provider_name == "mock":
                return ConnectionTestResult(
                    success=False,
                    failure_category="INVALID_CONFIGURATION",
                    message="A real provider is required for connection testing",
                )
            response = provider.test_connection()
            if not isinstance(response, LLMResponse):
                return ConnectionTestResult(
                    success=False,
                    failure_category="INVALID_RESPONSE",
                    message="Provider returned an invalid response",
                )
            return ConnectionTestResult(
                success=True,
                provider=response.provider,
                model=response.model,
                duration_ms=response.duration_ms,
                message="Connection successful",
            )
        except ProviderSettingsError:
            return ConnectionTestResult(
                success=False,
                failure_category="INVALID_CONFIGURATION",
                message="Provider settings are invalid",
            )
        except SecureStorageError:
            return ConnectionTestResult(
                success=False,
                failure_category="SECURE_STORAGE_UNAVAILABLE",
                message="Secure provider storage is unavailable",
            )
        except ProviderError as exc:
            return ConnectionTestResult(
                success=False,
                failure_category=exc.category.value,
                message=str(exc),
                duration_ms=exc.duration_ms,
            )
        except Exception:
            return ConnectionTestResult(
                success=False,
                failure_category="PROVIDER_ERROR",
                message="Provider connection failed",
            )

    def save(self, form: ProviderSettingsForm) -> ProviderSettingsSnapshot:
        return self.store.save(
            provider=form.provider,
            base_url=form.base_url,
            model=form.model,
            api_key=form.api_key,
        )

    def clear(self) -> ProviderSettingsSnapshot:
        self.store.clear()
        return self.store.snapshot()
