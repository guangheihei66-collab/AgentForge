"""AgentForge launcher state and owned service lifecycle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, MutableMapping, Sequence
from uuid import uuid4

from .process_session import (
    CREATE_NO_WINDOW,
    AgentForgeProcessSession,
    hidden_popen_options,
)


DEFAULT_DATA_ROOT = Path(r"D:\AgentProjectData\AgentForge")
BACKEND_PORT = 8000
FRONTEND_PORT = 5173


class ServiceState(str, Enum):
    STARTING = "Starting"
    RUNNING = "Running"
    STOPPED = "Stopped"
    FAILED = "Failed"


class LauncherState(str, Enum):
    STARTING = "Starting"
    RUNNING = "Running"
    STOPPING = "Stopping"
    STOPPED = "Stopped"
    ERROR = "Error"


@dataclass
class ServiceStatus:
    name: str
    state: ServiceState = ServiceState.STOPPED
    error: str | None = None
    pid: int | None = None
    owned: bool = False
    adopted: bool = False


@dataclass(frozen=True)
class PortOwner:
    """The minimum process metadata needed for safe port classification."""

    pid: int
    executable: str
    command_line: str
    cwd: str | None = None


def _canonical(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def _candidate_roots(root: Path) -> tuple[Path, ...]:
    current = _canonical(root)
    candidates: list[Path] = []
    for index in range(5):
        candidate = current if index == 0 else current.parent
        if candidate not in candidates:
            candidates.append(candidate)
        current = candidate
    return tuple(candidates)


def resolve_python(root: Path, environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the approved project interpreter without global fallback."""

    environment = os.environ if environ is None else environ
    override = str(environment.get("AGENTFORGE_PYTHON", "")).strip()
    if override:
        candidate = _canonical(Path(override))
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"Configured AGENTFORGE_PYTHON does not exist: {candidate}")

    for candidate_root in _candidate_roots(root):
        candidate = candidate_root / "backend" / ".venv" / "Scripts" / "python.exe"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "AgentForge backend virtual environment was not found under the launcher "
        "root or its bounded project ancestors."
    )


def resolve_pythonw(root: Path, environ: Mapping[str, str] | None = None) -> Path:
    python = resolve_python(root, environ)
    cfg = python.parent.parent / "pyvenv.cfg"
    if cfg.is_file():
        try:
            for line in cfg.read_text(encoding="utf-8").splitlines():
                name, separator, value = line.partition("=")
                if separator and name.strip().casefold() == "home":
                    base = _canonical(Path(value.strip())) / "pythonw.exe"
                    if base.is_file():
                        return base
        except OSError:
            pass
    if python.name.casefold() == "pythonw.exe":
        return python
    sibling = python.with_name("pythonw.exe")
    if sibling.is_file():
        return sibling
    raise FileNotFoundError(f"Windowless launcher interpreter was not found beside {python}")


def resolve_node_and_npm(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    environment = os.environ if environ is None else environ
    npm_override = str(environment.get("AGENTFORGE_NPM", "")).strip()
    npm = npm_override or shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which("node.exe" if os.name == "nt" else "node")
    if not node:
        raise FileNotFoundError("Node.js was not found on PATH.")
    if not npm:
        raise FileNotFoundError("npm was not found on PATH.")
    return node, npm


def launcher_data_root(environ: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    return _canonical(Path(environment.get("AGENTFORGE_DATA_ROOT", str(DEFAULT_DATA_ROOT))))


def launcher_environment(
    root: Path,
    session_token: str,
    environ: Mapping[str, str] | None = None,
    *,
    include_provider_secret: bool = False,
) -> dict[str, str]:
    """Build one child environment while preserving process-local cache settings.

    The backend receives the provider secret through its environment because
    that is the existing provider contract.  Frontend children use the safe
    default and never receive the secret.
    """

    environment = dict(os.environ if environ is None else environ)
    if not include_provider_secret:
        environment.pop("AGENTFORGE_LLM_API_KEY", None)
    backend_path = str(_canonical(root) / "backend")
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        backend_path + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    )
    environment.setdefault("AGENTFORGE_DATA_ROOT", str(DEFAULT_DATA_ROOT))
    environment["AGENTFORGE_LAUNCHER_ROOT"] = str(_canonical(root))
    environment["AGENTFORGE_LAUNCHER_SESSION"] = session_token
    return environment


def _safe_subprocess_options() -> dict[str, Any]:
    options = hidden_popen_options()
    options.update({"capture_output": True, "text": True})
    return options


def discover_port_owner(port: int) -> PortOwner | None:
    """Query one loopback listener without printing its command line."""

    if os.name != "nt":
        return None
    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$c=Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort {int(port)} "
        "-State Listen | Select-Object -First 1; "
        "if($c){$p=Get-CimInstance Win32_Process -Filter "
        "('ProcessId = ' + $c.OwningProcess); "
        "if($p){[PSCustomObject]@{pid=[int]$p.ProcessId; "
        "executable=[string]$p.Name; command_line=[string]$p.CommandLine} "
        "| ConvertTo-Json -Compress}}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            timeout=3,
            **_safe_subprocess_options(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout.strip())
        return PortOwner(
            pid=int(payload["pid"]),
            executable=str(payload.get("executable", "")),
            command_line=str(payload.get("command_line", "")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class LauncherController:
    def __init__(
        self,
        *,
        session: Any | None = None,
        root: Path | None = None,
        port_in_use: Callable[[int], bool] | None = None,
        health_check: Callable[[int], bool] | None = None,
        frontend_ready: Callable[[int], bool] | None = None,
        port_owner: Callable[[int], PortOwner | None] | None = None,
        python_path: Path | None = None,
        npm_path: str | None = None,
    ) -> None:
        self.root = _canonical(root or Path(__file__).resolve().parents[1])
        self.session_token = uuid4().hex
        self.data_root = launcher_data_root()
        self.runtime_dir = self.data_root / "runtime"
        self.log_dir = self.runtime_dir / "logs"
        self._real_session = session is None
        self.session = session or AgentForgeProcessSession(
            runtime_dir=self.runtime_dir,
            session_token=self.session_token,
        )
        self._custom_port_in_use = port_in_use is not None
        self.port_in_use = port_in_use or self._port_in_use
        self._custom_port_owner = port_owner is not None
        self.port_owner = port_owner or discover_port_owner
        self._custom_health_check = health_check is not None
        self.health_check = health_check or self._health_check
        self.frontend_ready = frontend_ready or (
            self.port_in_use if self._custom_health_check else self._frontend_http_ready
        )
        self.python_path = python_path
        self.npm_path = npm_path
        self.backend = ServiceStatus("Backend")
        self.frontend = ServiceStatus("Frontend")
        self.state = LauncherState.STOPPED
        self.error: str | None = None
        self._browser_opened = False
        self._operation_lock = threading.RLock()
        self.provider_settings_store: Any | None = None

    @staticmethod
    def _port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _health_check(port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    @staticmethod
    def _frontend_http_ready(port: int) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    def _commands(self) -> tuple[Sequence[str], Sequence[str]]:
        if self.python_path is not None:
            python = str(self.python_path)
        else:
            try:
                python = str(resolve_python(self.root))
            except FileNotFoundError:
                if self._real_session:
                    raise
                # Fake sessions in unit tests do not need a runnable venv.
                python = str(self.root / "backend" / ".venv" / "Scripts" / "python.exe")
        if self.npm_path is not None:
            npm = self.npm_path
        else:
            try:
                _, npm = resolve_node_and_npm()
            except FileNotFoundError:
                if self._real_session:
                    raise
                npm = "npm.cmd" if os.name == "nt" else "npm"
        backend = (
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(self.root / "backend"),
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        )
        frontend = (
            npm,
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--config",
            str(self.root / "frontend" / "vite.config.ts"),
        )
        return backend, frontend

    def _write_launcher_log(self, message: str) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / "launcher.log"
            if path.exists() and path.stat().st_size > 2 * 1024 * 1024:
                rotated = self.log_dir / "launcher.log.1"
                if rotated.exists():
                    rotated.unlink()
                path.replace(rotated)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except OSError:
            # Logging must not take down the service controller.
            return

    def _owner_matches(self, owner: PortOwner | None, kind: str) -> bool:
        if owner is None:
            return False
        command = owner.command_line.casefold()
        root = str(self.root).casefold().rstrip("\\/")
        if kind == "backend":
            return root in command and "app.main:app" in command and "uvicorn" in command
        frontend_root = str(self.root / "frontend").casefold().rstrip("\\/")
        return frontend_root in command or (root in command and "vite" in command)

    def _adopt_if_ready(self, kind: str, port: int, status: ServiceStatus) -> bool:
        if not self.port_in_use(port):
            return False
        owner = self.port_owner(port) if self._custom_port_owner or not self._custom_port_in_use else None
        if not self._owner_matches(owner, kind):
            self.error = f"{status.name} port {port} is already in use."
            status.error = self.error
            return False
        check = self.health_check if kind == "backend" else self.frontend_ready
        if not check(port):
            self.error = f"{status.name} port {port} is occupied by an AgentForge process that is not ready."
            status.error = self.error
            return False
        status.state = ServiceState.RUNNING
        status.pid = owner.pid if owner else None
        status.adopted = True
        status.owned = False
        self._write_launcher_log(f"Adopted healthy {kind} listener without spawning a duplicate process.")
        return True

    def _start_kwargs(self, label: str) -> dict[str, Any]:
        environment = launcher_environment(
            self.root,
            self.session_token,
            include_provider_secret=label.casefold() == "backend",
        )
        return {
            "cwd": str(self.root / label),
            "env": environment,
            "stdout_path": self.log_dir / f"{label}.log",
            "stderr_path": self.log_dir / f"{label}-error.log",
        }

    def _preflight_existing_services(self) -> bool:
        """Classify both listeners before starting either service.

        This prevents a foreign frontend port from causing a new backend to be
        spawned before startup eventually fails.
        """

        for kind, port, status in (
            ("backend", BACKEND_PORT, self.backend),
            ("frontend", FRONTEND_PORT, self.frontend),
        ):
            if status.state is ServiceState.RUNNING:
                continue
            if not self.port_in_use(port):
                continue
            if not self._adopt_if_ready(kind, port, status):
                return False
        return True

    def start_services(self) -> bool:
        with self._operation_lock:
            if self.backend.state is ServiceState.RUNNING and self.frontend.state is ServiceState.RUNNING:
                return True
            self.error = None
            self.state = LauncherState.STARTING
            self.backend.error = None
            self.frontend.error = None
            try:
                backend_command, frontend_command = self._commands()
                if not self._preflight_existing_services():
                    return self._startup_failed()
                if self.backend.state is not ServiceState.RUNNING:
                    self.backend.state = ServiceState.STARTING
                    process = self.session.start(
                        "backend",
                        backend_command,
                        **self._start_kwargs("backend"),
                    )
                    self.backend.pid = getattr(process, "pid", None)
                    self.backend.owned = True
                    self._write_launcher_log("Started owned backend process.")
                    if not self._wait_for(lambda: self.health_check(BACKEND_PORT)):
                        raise RuntimeError("Backend health check did not become ready.")
                    self.backend.state = ServiceState.RUNNING

                if self.frontend.state is not ServiceState.RUNNING:
                    self.frontend.state = ServiceState.STARTING
                    process = self.session.start(
                        "frontend",
                        frontend_command,
                        **self._start_kwargs("frontend"),
                    )
                    self.frontend.pid = getattr(process, "pid", None)
                    self.frontend.owned = True
                    self._write_launcher_log("Started owned frontend process.")
                    if not self._wait_for(lambda: self.frontend_ready(FRONTEND_PORT)):
                        raise RuntimeError("Frontend HTTP readiness check did not become ready.")
                    self.frontend.state = ServiceState.RUNNING
                self.state = LauncherState.RUNNING
                self._write_launcher_log("AgentForge services are ready.")
                return True
            except Exception as exc:
                self.error = str(exc)
                return self._startup_failed()

    def _startup_failed(self) -> bool:
        self.state = LauncherState.ERROR
        if self.backend.state is ServiceState.STARTING:
            self.backend.state = ServiceState.STOPPED
        if self.frontend.state is ServiceState.STARTING:
            self.frontend.state = ServiceState.FAILED
        self._write_launcher_log(f"ERROR: {self.error or 'startup failed'}")
        owned_labels = getattr(self.session, "owned_labels", lambda: ())()
        if owned_labels or any(status.owned for status in (self.backend, self.frontend)):
            try:
                self.session.stop()
            except Exception as exc:
                self._write_launcher_log(f"ERROR: owned process cleanup failed: {exc}")
        for status in (self.backend, self.frontend):
            if status.owned and not status.adopted:
                status.state = ServiceState.STOPPED
                status.pid = None
                status.owned = False
        return False

    @staticmethod
    def _wait_for(predicate: Callable[[], bool], timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.25)
        return predicate()

    @property
    def can_open(self) -> bool:
        return self.frontend.state is ServiceState.RUNNING

    def open_agentforge(self) -> bool:
        if not self.can_open:
            self.error = "AgentForge is not ready yet."
            return False
        opened = bool(webbrowser.open("http://127.0.0.1:5173"))
        if opened:
            self._write_launcher_log("Opened AgentForge browser.")
        return opened

    def open_agentforge_once(self) -> bool:
        if self._browser_opened:
            return False
        opened = self.open_agentforge()
        if opened:
            self._browser_opened = True
        return opened

    def stop_services(self) -> None:
        with self._operation_lock:
            self.state = LauncherState.STOPPING
            try:
                self.session.stop()
            finally:
                for status in (self.backend, self.frontend):
                    if not status.adopted:
                        status.state = ServiceState.STOPPED
                        status.pid = None
                        status.owned = False
                        status.error = None
                self.state = (
                    LauncherState.RUNNING
                    if self.backend.state is ServiceState.RUNNING or self.frontend.state is ServiceState.RUNNING
                    else LauncherState.STOPPED
                )
                self._write_launcher_log("Stopped owned AgentForge services.")

    def restart_services(self) -> bool:
        with self._operation_lock:
            self.stop_services()
            return self.start_services()


class StartupPoller:
    """Observe one startup operation from the Tk thread until it completes."""

    def __init__(
        self,
        controller: LauncherController,
        schedule: Callable,
        update: Callable[[], None],
        open_browser: Callable[[], None],
        delay_ms: int = 100,
    ):
        self.controller = controller
        self.schedule = schedule
        self.update = update
        self.open_browser = open_browser
        self.delay_ms = delay_ms
        self._startup_pending = False
        self._opened = False

    def start(self, worker: Callable[[], None]) -> None:
        self._startup_pending = True
        worker()
        self.schedule(self.delay_ms, self.tick)

    def complete(self) -> None:
        self._startup_pending = False

    def tick(self) -> None:
        self.update()
        starting = (
            self.controller.backend.state is ServiceState.STARTING
            or self.controller.frontend.state is ServiceState.STARTING
        )
        if self._startup_pending or starting:
            self.schedule(self.delay_ms, self.tick)
            return
        if self.controller.can_open and not self._opened:
            self._opened = True
            self.open_browser()


class ControllerWindowActions:
    """Keep service commands thin and make close-vs-exit behavior testable."""

    def __init__(
        self,
        controller: LauncherController,
        destroy: Callable[[], None],
        hide: Callable[[], None] | None = None,
    ):
        self.controller = controller
        self.destroy = destroy
        self.hide = hide

    def stop_services(self) -> None:
        self.controller.stop_services()

    def exit(self) -> None:
        self.controller.stop_services()
        self.destroy()

    def close_x(self) -> None:
        if self.hide is None:
            # Compatibility for the former headless action tests. The real
            # window always supplies ``hide`` and therefore remains in tray.
            self.exit()
            return
        self.hide()


def load_launcher_environment(
    root: Path,
    *,
    environ: MutableMapping[str, str] | None = None,
    store: Any | None = None,
    local_config_path: Path | None = None,
    force_persisted: bool = False,
) -> None:
    """Load local settings without creating an ambiguous mixed configuration.

    A non-empty provider environment value is an atomic operator override.  If
    it is absent, one complete saved user configuration is loaded instead.
    ``force_persisted`` is used only after an explicit save in the launcher UI.
    """

    target = os.environ if environ is None else environ
    config_path = local_config_path or (_canonical(root) / "launcher" / ".env.local")
    allowed = {
        "AGENTFORGE_PYTHON",
        "AGENTFORGE_LLM_PROVIDER",
        "AGENTFORGE_LLM_BASE_URL",
        "AGENTFORGE_LLM_MODEL",
        "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE",
    }
    if config_path.is_file():
        try:
            lines = config_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = ()
        for line in lines:
            trimmed = line.strip()
            if not trimmed or trimmed.startswith(("#", ";")) or "=" not in trimmed:
                continue
            name, value = (part.strip() for part in trimmed.split("=", 1))
            if name not in allowed or target.get(name):
                continue
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
            target[name] = value

    if store is None:
        from app.agents.providers.settings import ProviderSettingsStore

        store = ProviderSettingsStore()
    if force_persisted:
        saved = store.environment()
        for name in (
            "AGENTFORGE_LLM_PROVIDER",
            "AGENTFORGE_LLM_BASE_URL",
            "AGENTFORGE_LLM_MODEL",
            "AGENTFORGE_LLM_API_KEY",
            "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE",
        ):
            target.pop(name, None)
        target.update(saved)
        return

    if str(target.get("AGENTFORGE_LLM_PROVIDER", "")).strip():
        return
    target.update(store.environment())


def run_controller(root: Path) -> int:
    import tkinter as tk

    root = _canonical(root)
    backend_path = str(root / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from .provider_settings import (
        ConnectionTestResult,
        ProviderSettingsService,
        SubprocessProviderConnection,
    )

    def run_provider_connection(config: Any) -> ConnectionTestResult:
        try:
            python = resolve_python(root)
        except FileNotFoundError:
            return ConnectionTestResult(
                success=False,
                failure_category="PROVIDER_RUNTIME_UNAVAILABLE",
                message="Provider runtime is unavailable",
            )
        return SubprocessProviderConnection(
            python_path=python,
            backend_path=root / "backend",
        )(config)

    settings_service = ProviderSettingsService(connection_runner=run_provider_connection)
    load_launcher_environment(root, store=settings_service.store)
    os.environ["PYTHONPATH"] = str(root / "backend") + (
        os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
    )

    from .instance import InstanceCommand, InstanceOwnership
    from .tray import AgentForgeTray, TrayCommand

    window = tk.Tk()
    window.withdraw()
    ownership = InstanceOwnership(root)
    if not ownership.acquire():
        window.destroy()
        return 0

    controller = LauncherController(root=root)
    controller.provider_settings_store = settings_service.store
    tray: AgentForgeTray | None = None
    exiting = False
    operation_pending = False
    ui_queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]] = queue.Queue()

    window.title("AgentForge Launcher")
    window.geometry("470x360")
    window.resizable(False, False)

    tk.Label(window, text="AgentForge", font=("Segoe UI", 18, "bold")).pack(pady=(14, 2))
    tk.Label(window, text="Agent Operations Control", fg="#5b6472").pack(pady=(0, 10))
    launcher_text = tk.StringVar()
    backend_text = tk.StringVar()
    frontend_text = tk.StringVar()
    provider_text = tk.StringVar()
    database_text = tk.StringVar(value="Database: guarded by backend")
    message = tk.StringVar()
    for variable in (launcher_text, backend_text, frontend_text, provider_text, database_text):
        tk.Label(window, textvariable=variable, anchor="w").pack(fill="x", padx=36)
    tk.Label(window, textvariable=message, fg="#a33", wraplength=340).pack(pady=5)
    buttons = tk.Frame(window)
    buttons.pack(pady=4)

    def update() -> None:
        launcher_text.set(f"Launcher: {controller.state.value}")
        backend_text.set(f"Backend: {controller.backend.state.value}")
        frontend_text.set(f"Frontend: {controller.frontend.state.value}")
        provider = settings_service.snapshot()
        if provider.configured:
            provider_text.set(f"AI Provider: Configured · {provider.provider} · {provider.model}")
        elif provider.provider != "unconfigured":
            provider_text.set("AI Provider: Not configured (saved settings unavailable)")
        else:
            provider_text.set("AI Provider: Not configured")
        message.set(controller.error or "")
        open_button.configure(state=tk.NORMAL if controller.can_open else tk.DISABLED)
        restart_button.configure(state=tk.DISABLED if operation_pending else tk.NORMAL)

    def post_ui(callback: Callable[..., Any], *args: Any) -> None:
        """Marshal worker/native callbacks without calling Tk off-thread."""

        ui_queue.put((callback, args))

    def drain_ui_queue() -> None:
        while True:
            try:
                callback, args = ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception as exc:
                controller.error = str(exc)
                controller.state = LauncherState.ERROR
        window.after(50, drain_ui_queue)

    def show_window() -> None:
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except tk.TclError:
            pass

    def hide_window() -> None:
        window.withdraw()

    def run_operation(operation: Callable[[], Any]) -> None:
        nonlocal operation_pending
        if operation_pending:
            return
        operation_pending = True
        update()

        def worker() -> None:
            try:
                operation()
            finally:
                post_ui(finish_operation)

        threading.Thread(target=worker, name="AgentForgeLauncherOperation", daemon=True).start()

    def finish_operation() -> None:
        nonlocal operation_pending
        operation_pending = False
        update()

    def exit_launcher() -> None:
        nonlocal exiting
        if exiting:
            return
        exiting = True
        run_operation(controller.stop_services)

        def finish_exit() -> None:
            if operation_pending:
                window.after(50, finish_exit)
                return
            if tray is not None:
                tray.stop()
            ownership.release()
            window.destroy()

        window.after(50, finish_exit)

    def handle_command(command: InstanceCommand | TrayCommand) -> None:
        if command in (InstanceCommand.SHOW_OR_OPEN, TrayCommand.OPEN_LAUNCHER):
            show_window()
        elif command is TrayCommand.OPEN_AGENTFORGE:
            controller.open_agentforge()
        elif command in (InstanceCommand.STOP_SERVICES, TrayCommand.STOP_SERVICES):
            run_operation(controller.stop_services)
        elif command in (InstanceCommand.RESTART_SERVICES, TrayCommand.RESTART_SERVICES):
            run_operation(controller.restart_services)
        elif command in (InstanceCommand.EXIT, TrayCommand.EXIT):
            exit_launcher()

    def apply_saved_provider_settings() -> None:
        load_launcher_environment(
            controller.root,
            store=settings_service.store,
            force_persisted=True,
        )
        update()
        run_operation(controller.restart_services)

    def open_provider_settings() -> None:
        from .provider_dialog import open_provider_settings as open_dialog

        open_dialog(
            window,
            settings_service,
            on_saved=apply_saved_provider_settings,
            on_cleared=apply_saved_provider_settings,
        )

    def on_instance_command(command: InstanceCommand) -> None:
        post_ui(handle_command, command)

    ownership.on_command = on_instance_command
    tray = AgentForgeTray(lambda command: post_ui(handle_command, command))
    tray.start()

    actions = ControllerWindowActions(controller, exit_launcher, hide_window)
    open_button = tk.Button(buttons, text="Open AgentForge", command=controller.open_agentforge)
    open_button.grid(row=0, column=0, padx=3)
    restart_button = tk.Button(buttons, text="Restart", command=lambda: run_operation(controller.restart_services))
    restart_button.grid(row=0, column=1, padx=3)
    tk.Button(buttons, text="Stop Services", command=lambda: run_operation(controller.stop_services)).grid(
        row=0, column=2, padx=3
    )
    tk.Button(buttons, text="AI 设置 / AI Provider", command=open_provider_settings).grid(
        row=1, column=0, columnspan=3, pady=(8, 0)
    )
    tk.Button(window, text="Exit AgentForge", command=exit_launcher).pack(pady=(3, 8))
    window.protocol("WM_DELETE_WINDOW", actions.close_x)

    def startup_worker() -> None:
        try:
            controller.start_services()
        finally:
            post_ui(startup_poller.complete)

    startup_poller = StartupPoller(controller, window.after, update, controller.open_agentforge_once)
    show_window()
    update()
    window.after(50, drain_ui_queue)
    startup_poller.start(lambda: threading.Thread(target=startup_worker, daemon=True).start())
    window.mainloop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    raise SystemExit(run_controller(args.root))
