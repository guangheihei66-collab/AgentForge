"""Small Tk dialog for configuring the user-local real LLM provider."""

from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from .provider_settings import ProviderSettingsForm, ProviderSettingsService


def open_provider_settings(
    parent: Any,
    service: ProviderSettingsService,
    *,
    on_saved: Callable[[], None],
    on_cleared: Callable[[], None],
) -> Any:
    """Open the compact settings dialog and return its Toplevel instance."""

    import tkinter as tk
    from tkinter import messagebox, ttk

    snapshot = service.snapshot()
    dialog = tk.Toplevel(parent)
    dialog.title("AI Provider Settings / AI 设置")
    dialog.geometry("500x410")
    dialog.resizable(False, False)
    dialog.transient(parent)

    frame = tk.Frame(dialog, padx=22, pady=18)
    frame.pack(fill="both", expand=True)
    tk.Label(
        frame,
        text="AI Provider Settings",
        font=("Segoe UI", 15, "bold"),
        anchor="w",
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    tk.Label(
        frame,
        text="Configure once for Planner and AI Analyst. Secrets stay local to this Windows user.",
        fg="#5b6472",
        anchor="w",
        wraplength=450,
        justify="left",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 16))

    provider_var = tk.StringVar(
        value=snapshot.provider
        if snapshot.provider in service.supported_providers()
        else service.supported_providers()[0]
    )
    base_url_var = tk.StringVar(value=snapshot.base_url)
    model_var = tk.StringVar(value="" if snapshot.model == "not-configured" else snapshot.model)
    api_key_var = tk.StringVar()
    status_var = tk.StringVar(value="Test the candidate before saving.")
    saved_hint = tk.StringVar(
        value="•••••••• saved" if snapshot.credential_configured else "Not configured"
    )
    tested_signature: list[tuple[str, str, str, str | None] | None] = [None]
    testing = [False]

    def add_label(row: int, text: str) -> None:
        tk.Label(frame, text=text, anchor="w", fg="#53647c").grid(
            row=row, column=0, sticky="w", pady=6
        )

    add_label(2, "Provider")
    provider_box = ttk.Combobox(
        frame,
        textvariable=provider_var,
        values=service.supported_providers(),
        state="readonly",
        width=39,
    )
    provider_box.grid(row=2, column=1, sticky="ew", pady=6)
    add_label(3, "Base URL")
    tk.Entry(frame, textvariable=base_url_var, width=42).grid(
        row=3, column=1, sticky="ew", pady=6
    )
    add_label(4, "Model")
    tk.Entry(frame, textvariable=model_var, width=42).grid(
        row=4, column=1, sticky="ew", pady=6
    )
    add_label(5, "API Key")
    key_frame = tk.Frame(frame)
    key_frame.grid(row=5, column=1, sticky="ew", pady=6)
    tk.Entry(key_frame, textvariable=api_key_var, show="•", width=27).pack(
        side="left", fill="x", expand=True
    )
    tk.Label(key_frame, textvariable=saved_hint, fg="#6b778b", padx=8).pack(side="left")

    tk.Label(
        frame,
        textvariable=status_var,
        fg="#53647c",
        anchor="w",
        wraplength=450,
        justify="left",
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(11, 12))

    buttons = tk.Frame(frame)
    buttons.grid(row=7, column=0, columnspan=2, sticky="e")
    test_button = tk.Button(buttons, text="Test Connection / 测试连接")
    save_button = tk.Button(buttons, text="Save / 保存", state=tk.DISABLED)
    clear_button = tk.Button(
        buttons,
        text="Clear / 清除",
        state=tk.NORMAL
        if snapshot.provider != "unconfigured" or snapshot.validation_error
        else tk.DISABLED,
    )
    cancel_button = tk.Button(buttons, text="Cancel / 取消", command=dialog.destroy)
    test_button.pack(side="left", padx=3)
    save_button.pack(side="left", padx=3)
    clear_button.pack(side="left", padx=3)
    cancel_button.pack(side="left", padx=3)

    def form() -> ProviderSettingsForm:
        entered_key = api_key_var.get()
        return ProviderSettingsForm(
            provider=provider_var.get(),
            base_url=base_url_var.get(),
            model=model_var.get(),
            api_key=entered_key if entered_key else (None if snapshot.credential_configured else ""),
        )

    def signature(candidate: ProviderSettingsForm) -> tuple[str, str, str, str | None]:
        return (candidate.provider, candidate.base_url, candidate.model, candidate.api_key)

    def invalidate(*_args: object) -> None:
        tested_signature[0] = None
        save_button.configure(state=tk.DISABLED)

    for variable in (provider_var, base_url_var, model_var, api_key_var):
        variable.trace_add("write", invalidate)

    def finish_test(result, tested_candidate: tuple[str, str, str, str | None]) -> None:
        testing[0] = False
        test_button.configure(state=tk.NORMAL)
        candidate = form()
        if signature(candidate) != tested_candidate:
            tested_signature[0] = None
            save_button.configure(state=tk.DISABLED)
            status_var.set("Settings changed while testing; test the current settings again.")
            return
        if result.success:
            tested_signature[0] = tested_candidate
            save_button.configure(state=tk.NORMAL)
            provider = result.provider or candidate.provider
            model = result.model or candidate.model
            status_var.set(f"Connection successful: {provider} · {model}")
        else:
            tested_signature[0] = None
            save_button.configure(state=tk.DISABLED)
            status_var.set(
                f"Connection failed: {result.failure_category or 'PROVIDER_ERROR'}"
            )

    def test() -> None:
        if testing[0]:
            return
        candidate = form()
        tested_candidate = signature(candidate)
        testing[0] = True
        test_button.configure(state=tk.DISABLED)
        save_button.configure(state=tk.DISABLED)
        status_var.set("Testing real provider connection…")

        def worker() -> None:
            result = service.test_connection(candidate)
            try:
                dialog.after(0, lambda: finish_test(result, tested_candidate))
            except tk.TclError:
                return

        threading.Thread(target=worker, name="AgentForgeProviderConnection", daemon=True).start()

    def save() -> None:
        candidate = form()
        if tested_signature[0] != signature(candidate):
            status_var.set("Test the current settings successfully before saving.")
            return
        try:
            service.save(candidate)
        except Exception:
            status_var.set("Provider settings could not be saved.")
            return
        on_saved()
        dialog.destroy()

    def clear() -> None:
        if not messagebox.askyesno(
            "Clear AI provider",
            "Clear the saved AI provider configuration for this Windows user?",
            parent=dialog,
        ):
            return
        try:
            service.clear()
        except Exception:
            status_var.set("Provider settings could not be cleared.")
            return
        on_cleared()
        dialog.destroy()

    test_button.configure(command=test)
    save_button.configure(command=save)
    clear_button.configure(command=clear)
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.grab_set()
    return dialog
