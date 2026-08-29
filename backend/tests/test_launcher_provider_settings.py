from __future__ import annotations

from pathlib import Path

from app.agents.providers.settings import ProviderSettingsStore
from launcher.controller import launcher_environment, load_launcher_environment


SECRET = "launcher-generated-secret-not-for-output"


def test_persisted_provider_settings_load_for_backend_but_not_frontend(tmp_path):
    store = ProviderSettingsStore(config_path=tmp_path / "provider.json")
    store.save(
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        model="example-model",
        api_key=SECRET,
    )
    environment: dict[str, str] = {}

    load_launcher_environment(
        Path(r"D:\AgentProjects\AgentForge"),
        environ=environment,
        store=store,
        local_config_path=tmp_path / "missing.env",
    )

    backend = launcher_environment(
        Path(r"D:\AgentProjects\AgentForge"),
        "session",
        environment,
        include_provider_secret=True,
    )
    frontend = launcher_environment(
        Path(r"D:\AgentProjects\AgentForge"),
        "session",
        environment,
        include_provider_secret=False,
    )
    assert backend["AGENTFORGE_LLM_PROVIDER"] == "openai-compatible"
    assert backend["AGENTFORGE_LLM_API_KEY"] == SECRET
    assert "AGENTFORGE_LLM_API_KEY" not in frontend


def test_explicit_process_provider_override_wins_atomically(tmp_path):
    store = ProviderSettingsStore(config_path=tmp_path / "provider.json")
    store.save(
        provider="openai-compatible",
        base_url="https://saved.example/v1",
        model="saved-model",
        api_key=SECRET,
    )
    environment = {
        "AGENTFORGE_LLM_PROVIDER": "mock",
        "AGENTFORGE_LLM_BASE_URL": "",
        "AGENTFORGE_LLM_MODEL": "",
    }

    load_launcher_environment(
        Path(r"D:\AgentProjects\AgentForge"),
        environ=environment,
        store=store,
        local_config_path=tmp_path / "missing.env",
    )

    assert environment["AGENTFORGE_LLM_PROVIDER"] == "mock"
    assert environment.get("AGENTFORGE_LLM_BASE_URL", "") == ""
    assert "AGENTFORGE_LLM_API_KEY" not in environment


def test_launcher_commands_never_place_provider_secret_on_command_line(tmp_path):
    from launcher.controller import LauncherController

    controller = LauncherController(
        root=Path(r"D:\AgentProjects\AgentForge"),
        python_path=Path(r"D:\Python\python.exe"),
        npm_path="npm.cmd",
    )
    commands = controller._commands()
    assert all(SECRET not in " ".join(command) for command in commands)
