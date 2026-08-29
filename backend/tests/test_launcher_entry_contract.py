from __future__ import annotations

import os
from pathlib import Path

import pytest

from launcher.controller import resolve_python, resolve_pythonw


ROOT = Path(__file__).resolve().parents[2]


def test_feature_worktree_resolves_approved_parent_virtualenv():
    expected = Path(r"D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe")

    assert resolve_python(ROOT) == expected


def test_main_style_root_resolves_approved_virtualenv():
    main_root = Path(r"D:\AgentProjects\AgentForge")

    assert resolve_python(main_root) == main_root / "backend" / ".venv" / "Scripts" / "python.exe"


def test_windowless_launcher_uses_base_pythonw_for_venv_redirector():
    assert resolve_pythonw(ROOT) == Path(r"D:\Python\pythonw.exe")


def test_valid_python_override_wins_and_invalid_override_fails_closed(tmp_path):
    override = tmp_path / ("python.exe" if os.name == "nt" else "python")
    override.write_bytes(b"test")

    assert resolve_python(ROOT, {"AGENTFORGE_PYTHON": str(override)}) == override.resolve()
    with pytest.raises(FileNotFoundError, match="AGENTFORGE_PYTHON"):
        resolve_python(ROOT, {"AGENTFORGE_PYTHON": str(tmp_path / "missing.exe")})


def test_normal_launcher_has_no_demo_seed_side_effect():
    controller_source = (ROOT / "launcher" / "controller.py").read_text(encoding="utf-8")
    launcher_source = (ROOT / "launcher" / "agentforge_launcher.pyw").read_text(encoding="utf-8")

    assert "seed_demo" not in controller_source
    assert "seed_demo" not in launcher_source


def test_user_facing_entry_is_windowless_and_uses_launcher_module():
    vbs = (ROOT / "launcher" / "launch_agentforge.vbs").read_text(encoding="utf-8")
    assert "agentforge_launcher.pyw" in vbs
    assert "Run" in vbs
    assert ", 0, False" in vbs
