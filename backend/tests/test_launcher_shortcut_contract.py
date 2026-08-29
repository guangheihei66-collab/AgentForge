from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_shortcut_installer_has_main_and_feature_worktree_modes():
    source = (ROOT / "Create-AgentForge-Desktop-Shortcut.ps1").read_text(encoding="utf-8")

    assert "FeatureWorktree" in source
    assert "0x4E00" in source and "0x952E" in source
    assert "launch_agentforge.vbs" in source
    assert "CreateShortcut" in source


def test_start_and_stop_wrappers_use_windowless_control_entries():
    start = (ROOT / "launcher" / "start_agentforge.bat").read_text(encoding="utf-8")
    stop = (ROOT / "launcher" / "stop_agentforge.bat").read_text(encoding="utf-8")

    assert "launch_agentforge.vbs" in start
    assert "control_agentforge.vbs" in stop
    assert "seed_demo" not in start + stop


def test_launcher_documentation_no_longer_promises_automatic_demo_seeding():
    readme = (ROOT / "launcher" / "README.md").read_text(encoding="utf-8")
    deployment = (ROOT / "docs" / "deployment" / "README.md").read_text(encoding="utf-8")

    assert "seeds idempotent" not in readme
    assert "seeds idempotent" not in deployment
    assert "business data" in readme.lower()
