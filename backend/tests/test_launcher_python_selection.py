from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys


WORKTREE = Path(__file__).resolve().parents[2]
LAUNCHER = WORKTREE / "launcher" / "start_agentforge.ps1"
VALID_PYTHON = Path(sys.executable)


def run_selection(override: str | None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("AGENTFORGE_PYTHON", None)
    if override is not None:
        environment["AGENTFORGE_PYTHON"] = override
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(LAUNCHER),
            "-ResolvePythonOnly",
            "-LocalConfigPath",
            str(WORKTREE / "missing-local-config.env"),
        ],
        cwd=WORKTREE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )


def run_config(local_config: str | None, environment: dict[str, str] | None = None):
    config_path = None
    if local_config is not None:
        config_path = Path(os.environ.get("TEMP", ".")) / "agentforge-test-local.env"
        config_path.write_text(local_config, encoding="utf-8")
    child_environment = os.environ.copy()
    for name in (
        "AGENTFORGE_PYTHON",
        "AGENTFORGE_LLM_PROVIDER",
        "AGENTFORGE_LLM_BASE_URL",
        "AGENTFORGE_LLM_MODEL",
        "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE",
        "AGENTFORGE_LLM_API_KEY",
    ):
        child_environment.pop(name, None)
    child_environment.update(environment or {})
    command = [
        "powershell.exe",
        "-NoProfile",
        "-File",
        str(LAUNCHER),
        "-ResolveConfigOnly",
    ]
    if config_path is not None:
        command.extend(["-LocalConfigPath", str(config_path)])
    try:
        return subprocess.run(
            command,
            cwd=WORKTREE,
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
    finally:
        if config_path is not None:
            config_path.unlink(missing_ok=True)


def test_valid_explicit_python_override_is_selected():
    result = run_selection(str(VALID_PYTHON))

    assert result.returncode == 0
    assert str(VALID_PYTHON) in result.stdout


def test_empty_override_preserves_worktree_relative_default():
    result = run_selection(None)
    expected = WORKTREE / "backend" / ".venv" / "Scripts" / "python.exe"

    assert result.returncode == 0
    assert str(expected) in result.stdout


def test_invalid_explicit_override_fails_closed_without_default_fallback():
    invalid = WORKTREE / "missing-python.exe"
    result = run_selection(str(invalid))
    default = WORKTREE / "backend" / ".venv" / "Scripts" / "python.exe"

    assert result.returncode != 0
    assert "AGENTFORGE_PYTHON" in result.stdout + result.stderr
    assert str(default) not in result.stdout + result.stderr


def test_explicit_shell_python_override_wins_over_local_config():
    result = run_config(
        "AGENTFORGE_PYTHON=C:\\wrong\\python.exe\n",
        {"AGENTFORGE_PYTHON": str(VALID_PYTHON)},
    )

    assert result.returncode == 0
    config = json.loads(result.stdout)
    assert config["AGENTFORGE_PYTHON"] == str(VALID_PYTHON)
    assert "C:\\wrong\\python.exe" not in result.stdout


def test_local_config_supplies_python_and_non_secret_provider_fields():
    result = run_config(
        "\n".join(
            [
                f"AGENTFORGE_PYTHON={VALID_PYTHON}",
                "AGENTFORGE_LLM_PROVIDER=openai-compatible",
                "AGENTFORGE_LLM_BASE_URL=https://api.deepseek.com",
                "AGENTFORGE_LLM_MODEL=deepseek-v4-flash",
                "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE=json_object",
                "LOCAL_SECRET_SENTINEL=DO_NOT_PRINT",
            ]
        ),
    )

    assert result.returncode == 0
    config = json.loads(result.stdout)
    assert config["AGENTFORGE_PYTHON"] == str(VALID_PYTHON)
    assert config["AGENTFORGE_LLM_PROVIDER"] == "openai-compatible"
    assert config["AGENTFORGE_LLM_BASE_URL"] == "https://api.deepseek.com"
    assert config["AGENTFORGE_LLM_MODEL"] == "deepseek-v4-flash"
    assert config["AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE"] == "json_object"
    assert "DO_NOT_PRINT" not in result.stdout + result.stderr


def test_missing_local_config_preserves_default_python():
    result = run_config("")
    expected = WORKTREE / "backend" / ".venv" / "Scripts" / "python.exe"

    assert result.returncode == 0
    assert json.loads(result.stdout)["AGENTFORGE_PYTHON"] == str(expected)


def test_local_config_path_is_ignored_by_git():
    check = subprocess.run(
        ["git", "check-ignore", "-q", "launcher/.env.local"],
        cwd=WORKTREE,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0
