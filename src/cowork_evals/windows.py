"""The Win32 calls the CoWork driver makes on Windows, where macOS runs `open` and `osascript`.

Measured by a probe run on Windows 11 with the Claude-3p application: `os.startfile` on the
claude:// deep link opens a prefilled Cowork composer with the cursor in it, `SetForegroundWindow`
brings `claude.exe` to the front from a terminal, and `SendInput` reaches the composer.
docs/cowork_desktop.md.

Each function raises `OSError` on failure. The driver turns that into its code 3, as it does a
non-zero `osascript`. `user32` is loaded at the first call, so the module imports on every
platform.
"""

from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path
from typing import Any

# The executable stem of the CoWork process, which `frontmost` returns.
PROCESS = "claude"

# What the macOS `delay 0.8` after `activate` is for: the activation lands before the guard reads.
ACTIVATE_DELAY = 0.8

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x2
VK_CONTROL, VK_A, VK_DELETE, VK_RETURN = 0x11, 0x41, 0x2E, 0x0D

# MessageBoxTimeoutW: OK and Cancel, Cancel the default so a stray Return refuses, in front of
# everything. It returns IDOK, IDCANCEL, or MB_TIMEDOUT when nobody answered.
MB_FLAGS = 0x1 | 0x30 | 0x100 | 0x1000 | 0x10000 | 0x40000
IDOK, MB_TIMEDOUT = 1, 32000

_user32: Any = None
_kernel32: Any = None


def _load() -> tuple[Any, Any]:
    global _user32, _kernel32
    if _user32 is None:
        from ctypes import wintypes as w

        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        user32.EnumWindows.argtypes = [ctypes.c_void_p, w.LPARAM]
        user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        user32.GetWindowTextLengthW.argtypes = [w.HWND]
        user32.IsWindowVisible.argtypes = [w.HWND]
        user32.IsIconic.argtypes = [w.HWND]
        user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        user32.GetForegroundWindow.restype = w.HWND
        user32.SetForegroundWindow.argtypes = [w.HWND]
        user32.SendInput.argtypes = [w.UINT, ctypes.c_void_p, ctypes.c_int]
        user32.MessageBoxTimeoutW.argtypes = [w.HWND, w.LPCWSTR, w.LPCWSTR, w.UINT, w.WORD, w.DWORD]
        kernel32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel32.OpenProcess.restype = w.HANDLE
        kernel32.CloseHandle.argtypes = [w.HANDLE]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            w.HANDLE,
            w.DWORD,
            w.LPWSTR,
            ctypes.POINTER(w.DWORD),
        ]
        _user32, _kernel32 = user32, kernel32
    return _user32, _kernel32


def _process_of(hwnd: Any) -> str:
    """The executable stem of the process that owns a window, lower case, or empty."""
    user32, kernel32 = _load()
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size, buffer = ctypes.c_ulong(1024), ctypes.create_unicode_buffer(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).stem.lower()
    finally:
        kernel32.CloseHandle(handle)


def _cowork_window() -> Any:
    """The first visible, titled window of the CoWork process."""
    user32, _ = _load()
    found: list[Any] = []
    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)  # type: ignore[attr-defined]

    def collect(hwnd: Any, _: Any) -> bool:
        visible = user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd)
        if visible and _process_of(hwnd) == PROCESS:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback(collect), 0)
    if not found:
        raise OSError(f"no {PROCESS}.exe window: open CoWork first")
    return found[0]


def open_link(link: str) -> None:
    """Open the deep link with the registered claude:// handler."""
    os.startfile(link)  # type: ignore[attr-defined]


def activate() -> None:
    """Bring the CoWork window to the front, restoring it if it is minimized."""
    user32, _ = _load()
    hwnd = _cowork_window()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(ACTIVATE_DELAY)


def frontmost() -> str:
    """The executable stem of the foreground window's process, lower case."""
    user32, _ = _load()
    return _process_of(user32.GetForegroundWindow())


def _send(keys: list[tuple[int, bool]]) -> None:
    """SendInput for (virtual key, key up). Fewer events taken than given is an error."""
    user32, _ = _load()

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class MOUSEINPUT(ctypes.Structure):  # sizes the union, which SendInput checks
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_void_p),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", INPUTUNION)]

    inputs = (INPUT * len(keys))()
    for index, (vk, up) in enumerate(keys):
        inputs[index].type = INPUT_KEYBOARD
        inputs[index].u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    sent = user32.SendInput(len(keys), inputs, ctypes.sizeof(INPUT))
    if sent != len(keys):
        raise OSError(f"SendInput took {sent} of {len(keys)} key events: {ctypes.get_last_error()}")


def clear() -> None:
    """Select all in the composer and delete it: Ctrl+A, Delete."""
    _send(
        [(VK_CONTROL, False), (VK_A, False), (VK_A, True), (VK_CONTROL, True)]
        + [(VK_DELETE, False), (VK_DELETE, True)]
    )


def press_return() -> None:
    _send([(VK_RETURN, False), (VK_RETURN, True)])


def consent(message: str, title: str, timeout: float) -> bool:
    """Ask for the keyboard. OK or no answer within the timeout is yes, Cancel is no."""
    user32, _ = _load()
    answer = user32.MessageBoxTimeoutW(None, message, title, MB_FLAGS, 0, int(timeout * 1000))
    return answer in (IDOK, MB_TIMEDOUT)
