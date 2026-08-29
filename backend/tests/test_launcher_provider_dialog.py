from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compact_provider_settings_dialog_exposes_only_the_approved_flow():
    source = (ROOT / "launcher" / "provider_dialog.py").read_text(encoding="utf-8")

    for label in (
        "AI Provider Settings / AI 设置",
        "Provider",
        "Base URL",
        "Model",
        "API Key",
        "Test Connection / 测试连接",
        "Save / 保存",
        "Cancel / 取消",
        "Clear / 清除",
    ):
        assert label in source
    assert "service.test_connection(candidate)" in source
    assert "save_button = tk.Button(buttons, text=\"Save / 保存\", state=tk.DISABLED)" in source
    assert "messagebox.askyesno" in source
    assert "dialog.grab_set()" in source


def test_provider_settings_dialog_does_not_render_saved_secret():
    source = (ROOT / "launcher" / "provider_dialog.py").read_text(encoding="utf-8")

    assert "snapshot.api_key" not in source
    assert "saved_hint" in source
    assert 'show="•"' in source
