from __future__ import annotations

import os
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
        ["powershell.exe", "-NoProfile", "-File", str(LAUNCHER), "-ResolvePythonOnly"],
        cwd=WORKTREE,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )


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
