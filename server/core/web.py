"""Open a URL on the PC and put the browser in front of the user.

`webbrowser.open()` starts the browser but Windows' foreground lock usually
keeps it behind the active window, which is useless when the phone is the thing
being touched. This opens the URL and then raises the browser window itself.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import sys
import threading
import time
import webbrowser

log = logging.getLogger("deskgadget.web")

# Browsers we are willing to raise. Anything else is left alone.
BROWSER_EXES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "iexplore.exe",
    "librewolf.exe",
    "zen.exe",
    "arc.exe",
}

_SW_RESTORE = 9


def _is_windows() -> bool:
    return sys.platform == "win32"


def _browser_windows() -> list[int]:
    """Visible top-level browser windows, in z-order (top first)."""
    user32 = ctypes.windll.user32
    found: list[int] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            import psutil

            name = psutil.Process(pid.value).name().lower()
        except Exception:
            return True
        if name in BROWSER_EXES:
            found.append(hwnd)
        return True

    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return found


def _raise(hwnd: int) -> bool:
    """Bring `hwnd` to the front, defeating the foreground lock if needed."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)

    foreground = user32.GetForegroundWindow()
    if foreground == hwnd:
        return True

    fg_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    my_thread = kernel32.GetCurrentThreadId()
    attached = False
    try:
        if fg_thread and fg_thread != my_thread:
            attached = bool(user32.AttachThreadInput(my_thread, fg_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SetFocus(hwnd)
        except Exception:
            pass
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False
    finally:
        if attached:
            try:
                user32.AttachThreadInput(my_thread, fg_thread, False)
            except Exception:
                pass


def _raise_soon(before: set[int], attempts: int = 8) -> None:
    """Wait for the browser window, then raise it."""
    for _ in range(attempts):
        time.sleep(0.4)
        try:
            windows = _browser_windows()
        except Exception:
            return
        if not windows:
            continue
        # a window that appeared after we opened the URL is the one to raise;
        # otherwise fall back to the topmost browser window
        fresh = [hwnd for hwnd in windows if hwnd not in before]
        for hwnd in (fresh or windows):
            if _raise(hwnd):
                return


def open_url(url: str, *, focus: bool = True) -> bool:
    """Open `url` with the default handler and bring it to the foreground.

    Returns False only when the URL could not be handed to the OS at all.
    """
    if not url:
        return False

    before: set[int] = set()
    if focus and _is_windows():
        try:
            before = set(_browser_windows())
        except Exception:
            before = set()

    opened = False
    try:
        if _is_windows():
            os.startfile(url)  # type: ignore[attr-defined]
            opened = True
        else:
            opened = bool(webbrowser.open(url))
    except Exception:
        log.exception("could not open %s", url)
        return False

    if opened and focus and _is_windows():
        threading.Thread(target=_raise_soon, args=(before,), daemon=True).start()
    return opened
