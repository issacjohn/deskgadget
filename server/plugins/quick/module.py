"""Quick actions: safe one-tap Windows commands."""
from __future__ import annotations

import ctypes
import logging

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.quick")

VK_LWIN = 0x5B
VK_SHIFT = 0x10
KEY_D = 0x44
KEY_S = 0x53
HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
KEYEVENTF_KEYUP = 0x0002


def _combo(*keys: int) -> None:
    user32 = ctypes.windll.user32
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)

    async def on_action(self, action: str, payload: dict) -> None:
        try:
            if action == "lock":
                ctypes.windll.user32.LockWorkStation()
                await self.hub.notify("PC locked")
            elif action == "monitor_off":
                ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
            elif action == "show_desktop":
                _combo(VK_LWIN, KEY_D)
            elif action == "screenshot":
                _combo(VK_LWIN, VK_SHIFT, KEY_S)
                await self.hub.notify("Snipping tool open")
        except Exception:
            log.exception("quick action failed: %s", action)

    def page(self) -> dict:
        return {
            "blocks": [
                {
                    "type": "controls",
                    "style": "pill",
                    "items": [
                        {"id": "lock", "icon": "mute", "label": "Lock PC"},
                        {"id": "monitor_off", "icon": "mute", "label": "Screen off"},
                        {"id": "show_desktop", "icon": "grid", "label": "Desktop"},
                        {"id": "screenshot", "icon": "camera", "label": "Screenshot"},
                    ],
                },
                {
                    "type": "kv",
                    "items": [
                        {"label": "Lock", "value": "Win+L"},
                        {"label": "Screenshot", "value": "Win+Shift+S"},
                        {"label": "Desktop", "value": "Win+D"},
                    ],
                },
            ]
        }
