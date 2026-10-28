"""Windows input / window helpers for the LYCO RECO BEATS replay bot.

Only external input simulation is used (SendInput with scan codes).  No process
injection, no memory access, no game file modification.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

SCAN_SPACE = 0x39

VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(scan: int, flags: int) -> None:
    inp = INPUT(
        type=INPUT_KEYBOARD,
        u=_INPUTUNION(ki=KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)),
    )
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def key_down(scan: int = SCAN_SPACE) -> None:
    _send(scan, KEYEVENTF_SCANCODE)


def key_up(scan: int = SCAN_SPACE) -> None:
    _send(scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def ensure_admin(argv: list[str] | None = None) -> None:
    """Re-launch the current script elevated (UAC prompt) and exit this process."""
    if is_admin():
        return
    if argv is None:
        argv = sys.argv
    script = os.path.abspath(argv[0])
    params = subprocess.list2cmdline([script, *argv[1:]])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, os.getcwd(), 1
    )
    if ret <= 32:
        raise SystemExit(f"elevation failed (ShellExecuteW={ret}); run the terminal as administrator")
    raise SystemExit(0)


def get_async_key_state(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class KeyWatcher:
    """Edge-triggered global hotkey polling (works even when another window is focused)."""

    def __init__(self, vk: int):
        self.vk = vk
        self._last = False

    def pressed(self) -> bool:
        state = get_async_key_state(self.vk)
        edge = state and not self._last
        self._last = state
        return edge


def _process_name(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_game_window(exe_names: tuple[str, ...] = ("nikke.exe", "nikke_launcher.exe")) -> int:
    """Return the HWND of the first visible top-level window owned by the game."""
    found: list[int] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _process_name(pid.value)
        if name in exe_names:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found[0] if found else 0


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def is_foreground(hwnd: int) -> bool:
    return user32.GetForegroundWindow() == hwnd


def bring_to_front(hwnd: int) -> bool:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    return is_foreground(hwnd)


def begin_timer_precision() -> None:
    """Request 1 ms system timer resolution so time.sleep() can be accurate."""
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:  # noqa: BLE001
        pass


def end_timer_precision() -> None:
    try:
        ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:  # noqa: BLE001
        pass
