"""Windows single-instance ownership and activation signals."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import os
from pathlib import Path
import threading
import time
from typing import Callable


class InstanceCommand(StrEnum):
    SHOW_OR_OPEN = "show_or_open"
    STOP_SERVICES = "stop_services"
    RESTART_SERVICES = "restart_services"
    EXIT = "exit"


ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


def _installation_key(root: Path) -> str:
    canonical = str(root.expanduser().resolve()).casefold()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class InstanceNames:
    mutex: str
    events: dict[InstanceCommand, str]


def names_for_root(root: Path) -> InstanceNames:
    key = _installation_key(root)
    prefix = f"Local\\AgentForgeLauncher.{key}"
    return InstanceNames(
        mutex=f"{prefix}.mutex",
        events={command: f"{prefix}.{command.value}" for command in InstanceCommand},
    )


if os.name == "nt":
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _KERNEL32.CreateMutexW.restype = wintypes.HANDLE
    _KERNEL32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _KERNEL32.CreateEventW.restype = wintypes.HANDLE
    _KERNEL32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _KERNEL32.OpenEventW.restype = wintypes.HANDLE
    _KERNEL32.SetEvent.argtypes = [wintypes.HANDLE]
    _KERNEL32.SetEvent.restype = wintypes.BOOL
    _KERNEL32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.WaitForMultipleObjects.restype = wintypes.DWORD
    _KERNEL32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _KERNEL32.ReleaseMutex.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


_FALLBACK_LOCK = threading.Lock()
_FALLBACK_OWNERS: dict[str, "InstanceOwnership"] = {}


class InstanceOwnership:
    """Own one root-scoped launcher and receive commands from contenders."""

    def __init__(
        self,
        root: Path,
        *,
        on_command: Callable[[InstanceCommand], None] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        names = names_for_root(self.root)
        self.mutex_name = names.mutex
        self.event_names = names.events
        self.on_command = on_command or (lambda _: None)
        self._acquired = False
        self._stopping = threading.Event()
        self._listener: threading.Thread | None = None
        self._mutex = None
        self._events: dict[InstanceCommand, object] = {}

    def acquire(self) -> bool:
        if self._acquired:
            return True
        self._stopping.clear()
        if os.name != "nt":
            return self._acquire_fallback()

        ctypes.set_last_error(0)
        mutex = _KERNEL32.CreateMutexW(None, True, self.mutex_name)
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            _KERNEL32.CloseHandle(mutex)
            self.signal(self.root, InstanceCommand.SHOW_OR_OPEN)
            return False

        created: dict[InstanceCommand, object] = {}
        try:
            for command, name in self.event_names.items():
                event = _KERNEL32.CreateEventW(None, False, False, name)
                if not event:
                    raise ctypes.WinError(ctypes.get_last_error())
                created[command] = event
            self._mutex = mutex
            self._events = created
            self._acquired = True
            self._listener = threading.Thread(
                target=self._listen_windows,
                name="AgentForgeLauncherSignals",
                daemon=True,
            )
            self._listener.start()
            return True
        except BaseException:
            for event in created.values():
                _KERNEL32.CloseHandle(event)
            _KERNEL32.ReleaseMutex(mutex)
            _KERNEL32.CloseHandle(mutex)
            raise

    def release(self) -> None:
        if not self._acquired:
            return
        self._stopping.set()
        if os.name != "nt":
            with _FALLBACK_LOCK:
                if _FALLBACK_OWNERS.get(self.mutex_name) is self:
                    del _FALLBACK_OWNERS[self.mutex_name]
            self._acquired = False
            return

        listener = self._listener
        if listener is not None:
            listener.join(timeout=1.5)
        for event in self._events.values():
            _KERNEL32.CloseHandle(event)
        if self._mutex:
            _KERNEL32.ReleaseMutex(self._mutex)
            _KERNEL32.CloseHandle(self._mutex)
        self._events = {}
        self._mutex = None
        self._listener = None
        self._acquired = False

    close = release

    @classmethod
    def signal(cls, root: Path, command: InstanceCommand) -> bool:
        names = names_for_root(Path(root).expanduser().resolve())
        if os.name != "nt":
            with _FALLBACK_LOCK:
                owner = _FALLBACK_OWNERS.get(names.mutex)
            if owner is None or not owner._acquired:
                return False
            threading.Thread(
                target=owner._dispatch,
                args=(command,),
                name="AgentForgeLauncherFallbackSignal",
                daemon=True,
            ).start()
            return True

        event_name = names.events[command]
        for _ in range(20):
            event = _KERNEL32.OpenEventW(
                EVENT_MODIFY_STATE | SYNCHRONIZE,
                False,
                event_name,
            )
            if event:
                success = bool(_KERNEL32.SetEvent(event))
                _KERNEL32.CloseHandle(event)
                if success:
                    return True
            time.sleep(0.05)
        return False

    def _acquire_fallback(self) -> bool:
        with _FALLBACK_LOCK:
            if self.mutex_name in _FALLBACK_OWNERS:
                owner = _FALLBACK_OWNERS[self.mutex_name]
                threading.Thread(
                    target=owner._dispatch,
                    args=(InstanceCommand.SHOW_OR_OPEN,),
                    daemon=True,
                ).start()
                return False
            _FALLBACK_OWNERS[self.mutex_name] = self
            self._acquired = True
            return True

    def _listen_windows(self) -> None:
        commands = tuple(self.event_names)
        handles = tuple(self._events[command] for command in commands)
        handle_array = (ctypes.c_void_p * len(handles))(*handles)
        while not self._stopping.is_set():
            result = _KERNEL32.WaitForMultipleObjects(
                len(handles),
                handle_array,
                False,
                250,
            )
            if result == WAIT_TIMEOUT:
                continue
            index = result - WAIT_OBJECT_0
            if 0 <= index < len(commands):
                self._dispatch(commands[index])

    def _dispatch(self, command: InstanceCommand) -> None:
        if self._stopping.is_set():
            return
        try:
            self.on_command(command)
        except Exception:
            # Activation must not terminate the owner thread or release the mutex.
            return
