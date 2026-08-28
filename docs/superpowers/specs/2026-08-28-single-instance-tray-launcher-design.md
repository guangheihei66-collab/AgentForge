# AgentForge Windows Single-Instance Tray Launcher

Date: 2026-08-28

Status: HUMAN-approved bounded implementation design

## Goal

Make the existing AgentForge launcher behave like a normal Windows
application: one compact launcher, hidden backend/frontend services, a
system-tray lifecycle, safe activation on repeated starts, and no business
data created merely by starting the application.

This remains launcher polish. It does not change the Agent workflow, backend
API, Analyst architecture, approval boundary, ToolGateway, CapabilityResolver,
Project Authority, or database schema.

## Architecture

The user-facing entry is a Windows Script Host (`wscript.exe`) wrapper that
resolves its own installation root and launches a `pythonw.exe`-style Python
GUI entry without a console window. The GUI uses Tkinter, which is already
available through the approved Python runtime. A small native Win32 tray
adapter uses `Shell_NotifyIconW`; no new tray framework is introduced.

The launcher is divided into four testable responsibilities:

- `instance.py`: Windows named Mutex ownership and named Event activation.
  The mutex name includes a canonical-root hash so main and feature worktrees
  are independent installations. The OS releases the mutex after a crash;
  there is no manually managed stale lock file.
- `process_session.py`: hidden child creation, Job Object ownership, bounded
  termination, and identity checks. Only processes started or safely adopted
  by the current session can be stopped.
- `controller.py`: service state machine, approved interpreter resolution,
  port conflict checks, health/readiness checks, browser-open-once behavior,
  and no-side-effect startup. It never seeds demo or business records.
- `tray.py` and `agentforge_launcher.pyw`: compact window, tray menu,
  activation dispatch, close-to-tray behavior, and exit semantics.

## Lifecycle

1. Resolve root from the entry location and acquire the root-scoped Mutex.
2. If ownership already exists, signal the named Event and exit immediately.
3. Initialize only infrastructure tables if needed; never seed Tasks,
   Projects, Approvals, ToolExecutions, Evidence, or business audit records.
4. Validate the approved Python interpreter and both expected ports.
5. Start backend and frontend with hidden Windows process creation, then wait
   for backend health and frontend HTTP readiness.
6. Show compact status and open the browser once after readiness.
7. Keep the window available; X hides it to the tray. Tray commands dispatch
   Open AgentForge, Open Launcher, Stop Services, Restart Services, and Exit.
8. Stop/Restart act only on verified owned process identities. Exit removes
   the tray icon, closes the session Job Object, releases the Mutex/Event, and
   terminates the GUI.

## Process and port safety

Each managed service records PID, creation time, executable identity, command
line, root, and session token in memory for the active launcher. Before any
stop, the identity is revalidated to protect against PID reuse. A listener on
8000 or 5173 is never killed merely because it is Python or Node. An unknown
occupant produces a clear launcher error. A correctly identified existing
AgentForge service may be reported as reusable, but the current session does
not claim stop authority unless it started or explicitly adopted that process.

The Windows Job Object uses kill-on-close for children started by the current
session. Normal stop uses bounded graceful termination followed by bounded
escalation against the verified owned tree only. No infinite auto-restart is
implemented.

## No-console and configuration boundary

The desktop path uses `wscript.exe` and resolves `pythonw.exe` beside the
approved `AGENTFORGE_PYTHON` interpreter when possible. Service children use
`CREATE_NO_WINDOW`/hidden startup information. Provider and data-root
environment variables are inherited unchanged; the launcher does not force
Mock or rewrite provider configuration. Runtime logs remain under
`D:\AgentProjectData\AgentForge\runtime\logs`.

## Desktop shortcut

`Create-AgentForge-Desktop-Shortcut.ps1` is idempotent. It resolves the
current script's root, creates or updates one obvious shortcut named
`AgentForge 一键启动`, uses the repository-owned launcher icon when available
and a native application icon fallback otherwise, and points to the no-console
WScript entry. A `-FeatureWorktree` mode creates a clearly labeled RC test
shortcut without overwriting a main-installation shortcut.

## Error and tray behavior

Startup failures are shown in the compact launcher and written as bounded
messages to the external runtime log. A failure moves the launcher to ERROR;
it does not spawn replacements in a loop. Closing the window is not a service
operation. Stop Services leaves the tray controller alive. Restart waits for
verified termination before starting one stack. Exit performs the complete
shutdown and releases instance ownership.

## Verification

TDD covers Mutex/Event acquisition and activation, race-safe repeated starts,
root/interpreter resolution, no-console flags, port conflicts, process
identity/foreign-process protection, service stop/restart/exit, tray action
dispatch, browser-open-once behavior, shortcut idempotency, and the invariant
that normal startup creates no business records. A real Windows smoke then
uses the user-facing entry, checks visible processes and ports, repeats the
entry rapidly, exercises tray actions, and compares Task/Project/Approval/
ToolExecution counts before and after startup.

