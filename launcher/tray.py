"""Small native Windows notification-area integration for AgentForge."""

from __future__ import annotations

import ctypes
from enum import StrEnum
import os
import threading
from typing import Callable, Mapping
from uuid import uuid4


class TrayCommand(StrEnum):
    OPEN_AGENTFORGE = "open_agentforge"
    OPEN_LAUNCHER = "open_launcher"
    STOP_SERVICES = "stop_services"
    RESTART_SERVICES = "restart_services"
    EXIT = "exit"


class TrayCommandDispatcher:
    """Pure command router used by both the native tray and unit tests."""

    def __init__(self, handlers: Mapping[TrayCommand, Callable[[], object]]) -> None:
        self.handlers = dict(handlers)

    def dispatch(self, command: TrayCommand | str) -> object:
        try:
            normalized = command if isinstance(command, TrayCommand) else TrayCommand(command)
        except (TypeError, ValueError) as exc:
            raise KeyError(command) from exc
        handler = self.handlers.get(normalized)
        if handler is None:
            raise KeyError(normalized)
        return handler()


if os.name == "nt":
    from ctypes import wintypes

    WM_COMMAND = 0x0111
    WM_DESTROY = 0x0002
    WM_NULL = 0x0000
    WM_APP = 0x8000
    WM_TRAY = WM_APP + 17
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    NIM_ADD = 0x00000000
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    TPM_LEFTALIGN = 0x0000
    TPM_BOTTOMALIGN = 0x0020
    TPM_RETURNCMD = 0x0100
    TPM_NONOTIFY = 0x0080
    MF_STRING = 0x0000
    WS_EX_TOOLWINDOW = 0x00000080
    HWND_MESSAGE = ctypes.c_void_p(-3)
    IDI_APPLICATION = 32512

    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _SHELL32 = ctypes.WinDLL("shell32", use_last_error=True)
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _USER32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _USER32.DefWindowProcW.restype = ctypes.c_ssize_t
    _USER32.GetMessageW.argtypes = [
        ctypes.POINTER(_MSG) if "_MSG" in locals() else ctypes.c_void_p,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    _USER32.GetMessageW.restype = wintypes.BOOL
    _USER32.DispatchMessageW.argtypes = [ctypes.c_void_p]
    _USER32.DispatchMessageW.restype = ctypes.c_ssize_t
    _USER32.TranslateMessage.argtypes = [ctypes.c_void_p]
    _USER32.TranslateMessage.restype = wintypes.BOOL
    _USER32.LoadIconW.restype = ctypes.c_void_p
    _KERNEL32.GetCurrentThreadId.restype = wintypes.DWORD
    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class _MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", _POINT),
            ("lPrivate", wintypes.DWORD),
        ]

    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", ctypes.c_void_p),
            ("hIcon", ctypes.c_void_p),
            ("hCursor", ctypes.c_void_p),
            ("hbrBackground", ctypes.c_void_p),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class _NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", ctypes.c_void_p),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeout", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", ctypes.c_void_p),
        ]

    _MENU_IDS = {
        1001: TrayCommand.OPEN_AGENTFORGE,
        1002: TrayCommand.OPEN_LAUNCHER,
        1003: TrayCommand.STOP_SERVICES,
        1004: TrayCommand.RESTART_SERVICES,
        1005: TrayCommand.EXIT,
    }


class AgentForgeTray:
    """Own one notification-area icon and marshal menu actions to a callback."""

    def __init__(self, on_command: Callable[[TrayCommand], object]) -> None:
        self.on_command = on_command
        self._dispatcher = TrayCommandDispatcher(
            {command: lambda command=command: self.on_command(command) for command in TrayCommand}
        )
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._hwnd = None
        self._wndproc = None
        self._class_name = f"AgentForgeTrayWindow.{uuid4().hex}"

    def start(self) -> None:
        if os.name != "nt" or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_windows, name="AgentForgeTray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)

    def stop(self) -> None:
        if os.name != "nt":
            return
        self._stopping.set()
        if self._thread_id is not None:
            _USER32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def _emit(self, command: TrayCommand) -> None:
        try:
            self._dispatcher.dispatch(command)
        except KeyError:
            return

    def _run_windows(self) -> None:
        self._thread_id = int(_KERNEL32.GetCurrentThreadId())
        self._wndproc = _WNDPROC(self._window_proc)
        instance = _KERNEL32.GetModuleHandleW(None)
        window_class = _WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = instance
        window_class.lpszClassName = self._class_name
        _USER32.RegisterClassW(ctypes.byref(window_class))
        hwnd = _USER32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            self._class_name,
            "AgentForge",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            instance,
            None,
        )
        self._hwnd = hwnd
        if hwnd:
            self._add_icon(hwnd)
        self._ready.set()
        message = _MSG()
        while not self._stopping.is_set():
            result = _USER32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result <= 0:
                break
            _USER32.TranslateMessage(ctypes.byref(message))
            _USER32.DispatchMessageW(ctypes.byref(message))
        if hwnd:
            self._remove_icon(hwnd)
            _USER32.DestroyWindow(hwnd)
        self._hwnd = None

    def _add_icon(self, hwnd) -> None:
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        data.hWnd = hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = _USER32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        data.szTip = "AgentForge"
        _SHELL32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))

    @staticmethod
    def _remove_icon(hwnd) -> None:
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        data.hWnd = hwnd
        data.uID = 1
        _SHELL32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == WM_TRAY:
            if int(lparam) == WM_LBUTTONDBLCLK:
                self._emit(TrayCommand.OPEN_LAUNCHER)
            elif int(lparam) == WM_RBUTTONUP:
                self._show_menu(hwnd)
            return 0
        if message == WM_COMMAND:
            command = _MENU_IDS.get(int(wparam) & 0xFFFF)
            if command is not None:
                self._emit(command)
            return 0
        if message == WM_DESTROY:
            return 0
        return _USER32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_menu(self, hwnd) -> None:
        menu = _USER32.CreatePopupMenu()
        if not menu:
            return
        labels = {
            1001: "Open AgentForge",
            1002: "Open Launcher",
            1003: "Stop Services",
            1004: "Restart Services",
            1005: "Exit AgentForge",
        }
        try:
            for identifier, label in labels.items():
                _USER32.AppendMenuW(menu, MF_STRING, identifier, label)
            point = _POINT()
            _USER32.GetCursorPos(ctypes.byref(point))
            _USER32.SetForegroundWindow(hwnd)
            selected = _USER32.TrackPopupMenu(
                menu,
                TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x,
                point.y,
                0,
                hwnd,
                None,
            )
            if selected:
                command = _MENU_IDS.get(int(selected))
                if command is not None:
                    self._emit(command)
            _USER32.PostMessageW(hwnd, WM_NULL, 0, 0)
        finally:
            _USER32.DestroyMenu(menu)
