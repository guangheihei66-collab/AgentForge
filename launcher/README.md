# AgentForge One-Click Launcher

The normal user-facing entry is the desktop shortcut **AgentForge 一键启动**.
The reusable shortcut installer is:

```powershell
.\Create-AgentForge-Desktop-Shortcut.ps1
```

When testing this feature worktree, use the explicit RC mode:

```powershell
.\Create-AgentForge-Desktop-Shortcut.ps1 -FeatureWorktree
```

The shortcut targets Windows Script Host and the windowless `pythonw.exe`
launcher entry. It does not target `cmd.exe`, PowerShell, npm, Vite, uvicorn,
or console-mode Python.

Startup sequence:

1. Resolve the installation root from the launcher location.
2. Acquire the root-scoped native single-instance Mutex/Event boundary.
3. Resolve the approved project virtual environment.
4. Classify ports `8000` and `5173` without touching foreign listeners.
5. Start FastAPI and Vite as hidden, Job Object-owned children.
6. Wait for backend health and frontend HTTP readiness.
7. Open the browser once and keep a compact status window plus tray icon.

Normal startup is infrastructure-only and has no business data side effects. It does **not** seed Projects, Tasks,
Approvals, ToolExecutions, Evidence, or other business records. Demo fixtures
must be created explicitly through the documented demo flow.

The compact launcher includes **AI Provider Settings / AI 设置**. Configure
the supported real provider, HTTPS base URL, explicit model, and API key once;
click **Test Connection / 测试连接**, then **Save / 保存**. The probe uses the
real provider abstraction and creates no workflow records. Provider metadata is
stored in a user-local configuration outside the repository, and the API key
is protected with Windows user-scoped DPAPI. It is injected only into the
AgentForge-owned backend child, never into Vite/frontend, command-line
arguments, logs, diagnostics, or SQLite.

At startup, an explicit process environment provider override is authoritative;
otherwise the launcher loads one complete saved configuration. If neither is
usable, product mode reports `NOT_CONFIGURED` and never silently falls back to
Mock. `mock` remains an intentional offline development/test mode and is
labeled `MOCK` by diagnostics. The optional ignored `launcher/.env.local`
continues to support safe developer overrides; it must not contain a secret.

The settings dialog preserves a previously saved key when the masked field is
left unchanged. A failed candidate connection does not replace the active
configuration. Use **Clear / 清除** in the dialog to return to
`NOT_CONFIGURED`; this does not enable Mock.

Closing the compact window hides it to the system tray. Tray commands are
`Open AgentForge`, `Open Launcher`, `Stop Services`, `Restart Services`, and
`Exit AgentForge`. Only the current launcher's owned process session is stopped;
foreign Python, Node, and port owners are never killed.

Runtime logs and PID files remain outside the source tree at:

`D:\AgentProjectData\AgentForge\runtime\logs`

See `logs/README.md` for the storage boundary.

Legacy `start_agentforge.bat` and `stop_agentforge.bat` wrappers remain for
scripted use, but the desktop shortcut and root-level start entry use the
windowless VBS path.
