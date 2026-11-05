"""Window switcher: list the PC's open windows, focus or minimise one.

Uses only Win32 (`EnumWindows` + `SetForegroundWindow`), so there is no extra
dependency. Cloaked UWP windows and tool windows are filtered out.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging

import psutil

from core.base import Module as BaseModule
from core.launcher import register_icon_source

log = logging.getLogger("deskgadget.windows")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

DWMWA_CLOAKED = 14
GW_OWNER = 4
SW_RESTORE = 9


def _cloaked(hwnd: int) -> bool:
    try:
        value = wt.DWORD()
        dwmapi.DwmGetWindowAttribute(
            wt.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
        )
        return value.value != 0
    except Exception:
        return False


def _enumerate(limit: int) -> list[dict]:
    found: list[dict] = []

    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if user32.GetWindow(hwnd, GW_OWNER):
                return True
            if _cloaked(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value.strip()
            if not title:
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            app = ""
            exe = ""
            try:
                process = psutil.Process(pid.value)
                app = process.name().replace(".exe", "")
                exe = process.exe() or ""
            except Exception:
                pass
            found.append({"hwnd": int(hwnd), "title": title, "app": app, "exe": exe})
        except Exception:
            pass
        return True

    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return found[:limit]


def _focus(hwnd: int) -> bool:
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
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
            return user32.GetForegroundWindow() == hwnd
        finally:
            if attached:
                user32.AttachThreadInput(my_thread, fg_thread, False)
    except Exception:
        log.debug("focus failed", exc_info=True)
        return False


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.items: list[dict] = []
        self.message = ""

    async def update(self) -> None:
        try:
            limit = max(1, min(20, int(self.settings.get("limit", 8) or 8)))
        except Exception:
            limit = 8
        self.items = _enumerate(limit)

    async def on_action(self, action: str, payload: dict) -> None:
        raw = str(payload.get("id") or payload.get("url") or "")
        try:
            hwnd = int(raw)
        except ValueError:
            return
        target = next((w for w in self.items if w["hwnd"] == hwnd), None)
        if action == "focus":
            ok = _focus(hwnd)
            self.message = (
                f"Focused {target['app']}" if ok and target else "Windows refused the switch"
            )
            await self.hub.notify(self.message)
        self.push()

    def page(self) -> dict:
        blocks: list[dict] = []
        if not self.items:
            blocks.append(
                {
                    "type": "hero",
                    "label": "OPEN WINDOWS",
                    "value": "0",
                    "unit": "",
                    "sub": "Nothing to switch to",
                    "accent": self.accent,
                }
            )
            return {"blocks": blocks}

        blocks.append(
            {
                "type": "list",
                "title": f"{len(self.items)} OPEN WINDOWS",
                "items": [
                    {
                        "id": str(w["hwnd"]),
                        "title": w["title"],
                        "sub": w["app"],
                        "image": (
                            f"/icons/{register_icon_source(w['exe'])}"
                            if w.get("exe")
                            else ""
                        ),
                        "value": "↵",
                        "action": "focus",
                    }
                    for w in self.items
                ],
            }
        )
        return {"blocks": blocks}
