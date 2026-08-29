from __future__ import annotations

from launcher.controller import ControllerWindowActions, LauncherController
from launcher.tray import TrayCommand, TrayCommandDispatcher


def test_tray_command_dispatcher_routes_all_control_actions():
    received: list[TrayCommand] = []
    dispatcher = TrayCommandDispatcher(
        {command: lambda command=command: received.append(command) for command in TrayCommand}
    )

    for command in TrayCommand:
        dispatcher.dispatch(command)

    assert received == list(TrayCommand)


def test_close_x_hides_window_without_stopping_services():
    stopped = []
    hidden = []
    controller = LauncherController(session=type("Session", (), {"stop": lambda self: stopped.append(True)})())
    actions = ControllerWindowActions(controller, lambda: stopped.append("destroy"), lambda: hidden.append(True))

    actions.close_x()

    assert hidden == [True]
    assert stopped == []


def test_tray_dispatcher_rejects_unknown_command():
    dispatcher = TrayCommandDispatcher({TrayCommand.OPEN_LAUNCHER: lambda: None})

    try:
        dispatcher.dispatch("unknown")
    except KeyError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown tray command was accepted")
