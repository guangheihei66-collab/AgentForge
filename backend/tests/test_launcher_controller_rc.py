from __future__ import annotations

from pathlib import Path

from launcher.controller import (
    LauncherController,
    LauncherState,
    PortOwner,
    ServiceState,
)


class Session:
    def __init__(self) -> None:
        self.started: list[tuple[str, tuple[str, ...]]] = []
        self.stopped = 0

    def start(self, label, command, **_kwargs):
        self.started.append((label, tuple(command)))
        return type("Process", (), {"pid": len(self.started)})()

    def stop(self):
        self.stopped += 1

    def owned_labels(self):
        return tuple(label for label, _ in self.started)


def test_foreign_port_occupants_are_rejected_before_any_child_is_started():
    session = Session()
    controller = LauncherController(
        session=session,
        port_in_use=lambda port: port == 5173,
        port_owner=lambda _port: None,
    )

    assert controller.start_services() is False
    assert session.started == []
    assert session.stopped == 0
    assert controller.state is LauncherState.ERROR
    assert controller.frontend.state is ServiceState.STOPPED


def test_healthy_matching_listener_is_adopted_without_claiming_foreign_process():
    session = Session()
    root = Path(r"D:\AgentProjects\AgentForge")
    backend_owner = PortOwner(
        pid=1234,
        executable="python.exe",
        command_line=f'python -m uvicorn app.main:app --app-dir "{root / "backend"}"',
    )
    frontend_owner = PortOwner(
        pid=1235,
        executable="node.exe",
        command_line=f'node "{root / "frontend" / "node_modules" / ".bin" / "vite"}"',
    )
    controller = LauncherController(
        session=session,
        root=root,
        port_in_use=lambda _port: True,
        port_owner=lambda port: backend_owner if port == 8000 else frontend_owner,
        health_check=lambda _port: True,
        frontend_ready=lambda _port: True,
    )

    assert controller.start_services() is True
    assert session.started == []
    assert controller.backend.adopted is True
    assert controller.frontend.adopted is True
    assert controller.backend.owned is False


def test_restart_stops_owned_session_then_starts_one_new_pair():
    session = Session()
    active = False

    def port_in_use(_port):
        return active

    def start(label, command, **kwargs):
        nonlocal active
        active = True
        return Session.start(session, label, command, **kwargs)

    session.start = start
    controller = LauncherController(
        session=session,
        port_in_use=port_in_use,
        health_check=lambda _port: True,
        frontend_ready=lambda _port: True,
    )

    assert controller.start_services() is True
    active = False
    assert controller.restart_services() is True
    assert [label for label, _ in session.started] == ["backend", "frontend", "backend", "frontend"]
    assert session.stopped == 1


def test_browser_opens_once_after_readiness():
    opened: list[str] = []
    controller = LauncherController(session=Session(), port_in_use=lambda _port: False)
    controller.frontend.state = ServiceState.RUNNING
    controller.frontend_ready = lambda _port: True

    import launcher.controller as controller_module

    original = controller_module.webbrowser.open
    controller_module.webbrowser.open = lambda url: opened.append(url) or True
    try:
        assert controller.open_agentforge_once() is True
        assert controller.open_agentforge_once() is False
    finally:
        controller_module.webbrowser.open = original

    assert opened == ["http://127.0.0.1:5173"]
