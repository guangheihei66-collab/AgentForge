from launcher.controller import ControllerWindowActions, LauncherController, ServiceState, StartupPoller


class FakeProcess:
    def __init__(self):
        self.stopped = False


class FakeSession:
    def __init__(self):
        self.started = []
        self.stopped = 0

    def start(self, label, command, **kwargs):
        if label == "frontend":
            raise RuntimeError("frontend failed")
        process = FakeProcess()
        self.started.append((label, process))
        return process

    def stop(self):
        self.stopped += 1


def test_preexisting_port_is_not_stolen_and_start_does_not_launch_services():
    session = FakeSession()
    controller = LauncherController(session=session, port_in_use=lambda port: port == 5173)

    result = controller.start_services()

    assert result is False
    assert controller.error == "Frontend port 5173 is already in use."
    assert session.started == []
    assert session.stopped == 0
    assert controller.backend.state is ServiceState.STOPPED


def test_partial_start_failure_rolls_back_owned_services():
    session = FakeSession()
    controller = LauncherController(session=session, port_in_use=lambda _port: False, health_check=lambda _port: True)

    result = controller.start_services()

    assert result is False
    assert session.started[0][0] == "backend"
    assert session.stopped == 1
    assert controller.backend.state is ServiceState.STOPPED
    assert controller.frontend.state is ServiceState.FAILED


def test_stop_is_idempotent_and_open_requires_healthy_frontend():
    session = FakeSession()
    controller = LauncherController(session=session, port_in_use=lambda _port: False)
    controller.stop_services()
    controller.stop_services()

    assert session.stopped == 2
    assert controller.can_open is False


def test_stop_button_stops_services_without_destroying_controller():
    session = FakeSession()
    controller = LauncherController(session=session, port_in_use=lambda _port: False)
    destroyed = []
    actions = ControllerWindowActions(controller, lambda: destroyed.append(True))

    actions.stop_services()

    assert session.stopped == 1
    assert destroyed == []


def test_exit_and_close_x_stop_services_then_destroy_controller():
    for action_name in ("exit", "close_x"):
        session = FakeSession()
        controller = LauncherController(session=session, port_in_use=lambda _port: False)
        destroyed = []
        actions = ControllerWindowActions(controller, lambda: destroyed.append(True))

        getattr(actions, action_name)()

        assert session.stopped == 1
        assert destroyed == [True]


def test_default_commands_use_active_root_not_provider_hotfix_worktree(tmp_path):
    class HealthySession(FakeSession):
        def start(self, label, command, **kwargs):
            process = FakeProcess()
            self.started.append((label, process, kwargs))
            return process

    session = HealthySession()
    def port_in_use(port):
        return port == 5173 and len(session.started) >= 2
    controller = LauncherController(session=session, root=tmp_path, port_in_use=port_in_use, health_check=lambda _port: True)

    assert controller.start_services() is True

    assert [call[2]["cwd"] for call in session.started] == [str(tmp_path / "backend"), str(tmp_path / "frontend")]


def test_startup_poller_survives_first_tick_before_worker_state_transition():
    controller = LauncherController(session=FakeSession(), port_in_use=lambda _port: False)
    scheduled = []
    updates = []
    opened = []
    worker_started = []
    def tkinter_after(delay, callback):
        assert isinstance(delay, int)
        assert callable(callback)
        scheduled.append((delay, callback))

    poller = StartupPoller(controller, tkinter_after, lambda: updates.append(True), lambda: opened.append(True))

    poller.start(lambda: worker_started.append(True))
    assert controller.backend.state is ServiceState.STOPPED
    assert controller.frontend.state is ServiceState.STOPPED
    poller.tick()
    assert scheduled, "the first STOPPED observation must keep startup polling alive"
    assert opened == []

    controller.backend.state = ServiceState.RUNNING
    controller.frontend.state = ServiceState.RUNNING
    poller.complete()
    poller.tick()
    poller.tick()

    assert worker_started == [True]
    assert opened == [True]


def test_startup_poller_uses_tk_after_argument_order_for_start_and_reschedule():
    controller = LauncherController(session=FakeSession(), port_in_use=lambda _port: False)
    scheduled = []

    def tkinter_after(delay, callback):
        assert isinstance(delay, int)
        assert callable(callback)
        scheduled.append((delay, callback))

    poller = StartupPoller(controller, tkinter_after, lambda: None, lambda: None)
    poller.start(lambda: None)
    poller.tick()

    assert len(scheduled) == 2
