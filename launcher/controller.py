"""AgentForge Controller and owned service lifecycle."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

from .process_session import AgentForgeProcessSession


class ServiceState(str, Enum):
    STARTING = "Starting"
    RUNNING = "Running"
    STOPPED = "Stopped"
    FAILED = "Failed"


@dataclass
class ServiceStatus:
    name: str
    state: ServiceState = ServiceState.STOPPED
    error: str | None = None


class LauncherController:
    def __init__(
        self,
        *,
        session=None,
        root: Path | None = None,
        port_in_use: Callable[[int], bool] | None = None,
        health_check: Callable[[int], bool] | None = None,
    ):
        self.root = root or Path(__file__).resolve().parents[1]
        self.session = session or AgentForgeProcessSession()
        self.port_in_use = port_in_use or self._port_in_use
        self.health_check = health_check or self._health_check
        self.backend = ServiceStatus("Backend")
        self.frontend = ServiceStatus("Frontend")
        self.error: str | None = None
        self._stopped = False

    @staticmethod
    def _port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _health_check(port: int) -> bool:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    def _commands(self) -> tuple[Sequence[str], Sequence[str]]:
        python = os.environ.get("AGENTFORGE_PYTHON") or str(self.root / "backend" / ".venv" / "Scripts" / "python.exe")
        npm = "npm.cmd" if os.name == "nt" else "npm"
        return (
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            [npm, "run", "dev", "--", "--host", "127.0.0.1"],
        )

    def start_services(self) -> bool:
        if self.backend.state is ServiceState.RUNNING or self.frontend.state is ServiceState.RUNNING:
            return True
        self.error = None
        for port, label in ((8000, "Backend"), (5173, "Frontend")):
            if self.port_in_use(port):
                self.error = f"{label} port {port} is already in use."
                return False
        backend_command, frontend_command = self._commands()
        self.backend.state = ServiceState.STARTING
        try:
            self.session.start("backend", backend_command, cwd=str(self.root / "backend"))
            if not self._wait_for(lambda: self.health_check(8000)):
                raise RuntimeError("Backend health check did not become ready.")
            self.backend.state = ServiceState.RUNNING
            self.frontend.state = ServiceState.STARTING
            self.session.start("frontend", frontend_command, cwd=str(self.root / "frontend"))
            if not self._wait_for(lambda: self.port_in_use(5173)):
                raise RuntimeError("Frontend port 5173 did not become ready.")
            self.frontend.state = ServiceState.RUNNING
            return True
        except Exception as exc:
            self.error = str(exc)
            self.backend.state = ServiceState.STOPPED
            if self.frontend.state is ServiceState.STARTING:
                self.frontend.state = ServiceState.FAILED
            self.session.stop()
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
        return bool(webbrowser.open("http://127.0.0.1:5173"))

    def stop_services(self) -> None:
        self.session.stop()
        self.backend.state = ServiceState.STOPPED
        self.frontend.state = ServiceState.STOPPED
        self._stopped = True


class StartupPoller:
    """Observe one startup operation from the Tk thread until it completes."""

    def __init__(self, controller: LauncherController, schedule: Callable, update: Callable[[], None], open_browser: Callable[[], None], delay_ms: int = 100):
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
        starting = self.controller.backend.state is ServiceState.STARTING or self.controller.frontend.state is ServiceState.STARTING
        if self._startup_pending or starting:
            self.schedule(self.delay_ms, self.tick)
            return
        if self.controller.can_open and not self._opened:
            self._opened = True
            self.open_browser()


class ControllerWindowActions:
    """Keep window commands thin and make shutdown behavior testable."""

    def __init__(self, controller: LauncherController, destroy: Callable[[], None]):
        self.controller = controller
        self.destroy = destroy

    def stop_services(self) -> None:
        self.controller.stop_services()

    def exit(self) -> None:
        self.controller.stop_services()
        self.destroy()

    def close_x(self) -> None:
        self.exit()


def run_controller(root: Path) -> int:
    import tkinter as tk

    os.environ["PYTHONPATH"] = str(root / "backend")
    python = os.environ.get("AGENTFORGE_PYTHON") or str(root / "backend" / ".venv" / "Scripts" / "python.exe")
    for command in (
        [python, "-c", "from app.storage.database import init_db; init_db()"],
        [python, str(root / "scripts" / "seed_demo.py")],
    ):
        result = subprocess.run(command, cwd=str(root), env=os.environ.copy())
        if result.returncode != 0:
            raise RuntimeError("AgentForge startup bootstrap failed.")

    controller = LauncherController(root=root)
    window = tk.Tk()
    window.title("AgentForge")
    window.geometry("360x250")
    window.resizable(False, False)
    actions = ControllerWindowActions(controller, window.destroy)
    tk.Label(window, text="AgentForge", font=("Segoe UI", 18, "bold")).pack(pady=(18, 12))
    backend_text = tk.StringVar()
    frontend_text = tk.StringVar()
    message = tk.StringVar()
    tk.Label(window, textvariable=backend_text, anchor="w").pack(fill="x", padx=30)
    tk.Label(window, textvariable=frontend_text, anchor="w").pack(fill="x", padx=30)
    tk.Label(window, textvariable=message, fg="#a33", wraplength=300).pack(pady=6)
    buttons = tk.Frame(window)
    buttons.pack(pady=4)

    def update():
        backend_text.set(f"Backend: {controller.backend.state.value}")
        frontend_text.set(f"Frontend: {controller.frontend.state.value}")
        message.set(controller.error or "")
        open_button.configure(state=tk.NORMAL if controller.can_open else tk.DISABLED)

    poller = StartupPoller(controller, window.after, update, controller.open_agentforge)

    def start_worker():
        def worker():
            try:
                controller.start_services()
            finally:
                poller.complete()
        threading.Thread(target=worker, daemon=True).start()

    def stop():
        actions.stop_services()
        update()

    def close():
        actions.close_x()

    open_button = tk.Button(buttons, text="Open AgentForge", command=controller.open_agentforge)
    open_button.grid(row=0, column=0, padx=4)
    tk.Button(buttons, text="Stop Services", command=stop).grid(row=0, column=1, padx=4)
    tk.Button(buttons, text="Exit AgentForge", command=actions.exit).grid(row=0, column=2, padx=4)
    window.protocol("WM_DELETE_WINDOW", actions.close_x)
    update()
    poller.start(start_worker)
    window.mainloop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    raise SystemExit(run_controller(args.root))
