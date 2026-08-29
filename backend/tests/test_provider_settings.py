from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess

import pytest

from app.agents.providers.base import (
    LLMResponse,
    ProviderError,
    ProviderErrorCategory,
    StructuredOutputMode,
)
from app.agents.providers.settings import (
    ProviderSettingsStore,
    SecureStorageError,
    WindowsDPAPIProtector,
)
from launcher.provider_settings import (
    ConnectionTestResult,
    ProviderSettingsForm,
    ProviderSettingsService,
    SubprocessProviderConnection,
)


SECRET = "generated-test-provider-secret-not-for-output"


class RoundTripProtector:
    """Deterministic test double; Windows integration uses the real protector below."""

    def protect(self, value: bytes) -> bytes:
        return b"test-protected:" + base64.b64encode(value)

    def unprotect(self, value: bytes) -> bytes:
        prefix = b"test-protected:"
        if not value.startswith(prefix):
            raise SecureStorageError("Stored provider secret is unavailable")
        return base64.b64decode(value[len(prefix) :], validate=True)


def make_store(tmp_path: Path) -> ProviderSettingsStore:
    return ProviderSettingsStore(
        config_path=tmp_path / "provider.json",
        protector=RoundTripProtector(),
    )


def test_non_secret_provider_config_persists_outside_repository(tmp_path):
    store = make_store(tmp_path)

    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="example-model",
        api_key=SECRET,
    )

    assert store.config_path != Path(__file__).resolve().parents[2] / "provider.json"
    snapshot = store.snapshot()
    assert snapshot.provider == "openai-compatible"
    assert snapshot.base_url == "https://provider.example/v1"
    assert snapshot.model == "example-model"
    assert snapshot.credential_configured is True


def test_saved_real_provider_settings_use_json_object_mode(tmp_path):
    store = make_store(tmp_path)

    config = store.validate_candidate(
        provider="openai-compatible",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        api_key=SECRET,
    )

    assert config.structured_output_mode is StructuredOutputMode.JSON_OBJECT

    store.save(
        provider="openai-compatible",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        api_key=SECRET,
    )
    assert store.load_provider_config().structured_output_mode is StructuredOutputMode.JSON_OBJECT


def test_default_provider_config_is_user_local_and_not_worktree_bound(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    from app.agents.providers.settings import default_provider_config_path

    path = default_provider_config_path()
    assert path == tmp_path / "LocalAppData" / "AgentForge" / "config" / "provider.json"
    assert "evidence-ai-analyst-report" not in str(path)


def test_api_key_is_encrypted_and_round_trips_without_plaintext_on_disk(tmp_path):
    store = make_store(tmp_path)
    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="example-model",
        api_key=SECRET,
    )

    raw = store.config_path.read_bytes()
    assert SECRET.encode() not in raw
    assert store.load_provider_config().api_key == SECRET


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI integration")
def test_windows_dpapi_round_trip_is_user_protected():
    protector = WindowsDPAPIProtector()
    encrypted = protector.protect(SECRET.encode())
    assert encrypted != SECRET.encode()
    assert protector.unprotect(encrypted) == SECRET.encode()


def test_missing_or_corrupt_secure_secret_fails_closed(tmp_path):
    path = tmp_path / "provider.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "provider": "openai-compatible",
                "base_url": "https://provider.example/v1",
                "model": "example-model",
            }
        ),
        encoding="utf-8",
    )
    store = ProviderSettingsStore(config_path=path, protector=RoundTripProtector())
    assert store.snapshot().configured is False
    assert store.snapshot().provider != "mock"

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "provider": "openai-compatible",
                "base_url": "https://provider.example/v1",
                "model": "example-model",
                "api_key_dpapi": "not-base64",
            }
        ),
        encoding="utf-8",
    )
    assert store.snapshot().configured is False
    assert store.snapshot().provider != "mock"


def test_saved_key_is_preserved_when_candidate_does_not_replace_it(tmp_path):
    store = make_store(tmp_path)
    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="old-model",
        api_key=SECRET,
    )

    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="new-model",
        api_key=None,
    )

    config = store.load_provider_config()
    assert config.model == "new-model"
    assert config.api_key == SECRET

    reloaded = ProviderSettingsStore(
        config_path=store.config_path,
        protector=RoundTripProtector(),
    )
    assert reloaded.load_provider_config().api_key == SECRET


def test_failed_candidate_connection_does_not_replace_known_good_config(tmp_path):
    store = make_store(tmp_path)
    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="known-good",
        api_key=SECRET,
    )

    def fail(_config):
        raise ProviderError(ProviderErrorCategory.AUTHENTICATION_FAILED)

    service = ProviderSettingsService(store=store, provider_builder=fail)
    result = service.test_connection(
        ProviderSettingsForm(
            provider="openai-compatible",
            base_url="https://provider.example/v1",
            model="candidate",
            api_key="candidate-secret",
        )
    )

    assert isinstance(result, ConnectionTestResult)
    assert result.success is False
    assert result.failure_category == "AUTHENTICATION_FAILED"
    assert store.load_provider_config().model == "known-good"
    assert store.load_provider_config().api_key == SECRET


def test_connection_test_uses_real_provider_and_returns_sanitized_identity(tmp_path):
    store = make_store(tmp_path)
    calls = []

    class RealProvider:
        provider_name = "openai-compatible"
        model_name = "candidate-model"

        def test_connection(self):
            calls.append(True)
            return LLMResponse(
                payload={"status": "ok"},
                provider=self.provider_name,
                model=self.model_name,
                duration_ms=12,
                attempt_count=1,
            )

    def build(config):
        assert config.provider == "openai-compatible"
        assert config.api_key == "candidate-secret"
        return RealProvider()

    service = ProviderSettingsService(store=store, provider_builder=build)
    result = service.test_connection(
        ProviderSettingsForm(
            provider="openai-compatible",
            base_url="https://provider.example/v1",
            model="candidate-model",
            api_key="candidate-secret",
        )
    )

    assert result.success is True
    assert result.provider == "openai-compatible"
    assert result.model == "candidate-model"
    assert calls == [True]
    assert "candidate-secret" not in result.message


def test_provider_settings_service_rejects_mock_for_connection(tmp_path):
    service = ProviderSettingsService(store=make_store(tmp_path), provider_builder=lambda _: pytest.fail("Mock must not be built"))

    result = service.test_connection(
        ProviderSettingsForm(
            provider="mock",
            base_url="",
            model="",
            api_key="candidate-secret",
        )
    )

    assert result.success is False
    assert result.failure_category == "INVALID_CONFIGURATION"


def test_product_status_api_reports_unconfigured_without_mock_fallback(monkeypatch):
    monkeypatch.delenv("AGENTFORGE_LLM_PROVIDER", raising=False)
    from fastapi.testclient import TestClient

    from app.api.routes.providers import connection_state
    from app.main import app

    connection_state.reset()
    with TestClient(app) as client:
        response = client.get("/llm/provider")

    assert response.status_code == 200
    assert response.json()["provider"] == "unconfigured"
    assert response.json()["configured"] is False
    assert response.json()["model"] == "not-configured"
    assert response.json()["credential_configured"] is False
    assert response.json()["failure_category"] == "NOT_CONFIGURED"


def test_subprocess_provider_probe_passes_secret_only_through_environment(monkeypatch, tmp_path):
    store = make_store(tmp_path)
    config = store.validate_candidate(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="example-model",
        api_key=SECRET,
    )
    captured: dict[str, object] = {}

    def fake_run(command, *, env, **kwargs):
        captured["command"] = command
        captured["env"] = env
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            '{"ok":true,"provider":"openai-compatible","model":"example-model","duration_ms":7}\n',
            "",
        )

    monkeypatch.setattr("launcher.provider_settings.subprocess.run", fake_run)
    result = SubprocessProviderConnection(
        python_path=tmp_path / "python.exe",
        backend_path=tmp_path / "backend",
    )(config)

    assert result.success is True
    command = captured["command"]
    environment = captured["env"]
    assert isinstance(command, list)
    assert SECRET not in " ".join(command)
    assert isinstance(environment, dict)
    assert environment["AGENTFORGE_LLM_API_KEY"] == SECRET
    assert environment["PYTHONPATH"] == str(tmp_path / "backend")
    assert captured["kwargs"]["capture_output"] is True
    assert os.path.basename(str(command[0])) == "python.exe"
