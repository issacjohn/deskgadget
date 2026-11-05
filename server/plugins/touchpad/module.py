"""Touchpad: the phone becomes a trackpad for the PC.

One finger moves the pointer, a tap clicks, two fingers scroll, and the
buttons under the pad give you right/middle click without guesswork.
"""
from __future__ import annotations

import ctypes
import logging

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.touchpad")

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
    ctypes.windll.user32.mouse_event(flags, dx, dy, data, 0)


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self._rx = 0.0
        self._ry = 0.0

    def _scale(self) -> float:
        try:
            return max(0.25, min(3.0, float(self.settings.get("sensitivity", 1.0) or 1.0)))
        except Exception:
            return 1.0

    async def on_action(self, action: str, payload: dict) -> None:
        try:
            if action == "move":
                # keep sub-pixel movement so slow drags still feel smooth
                self._rx += float(payload.get("dx", 0)) * self._scale()
                self._ry += float(payload.get("dy", 0)) * self._scale()
                dx, dy = int(self._rx), int(self._ry)
                if dx or dy:
                    self._rx -= dx
                    self._ry -= dy
                    _mouse(MOUSEEVENTF_MOVE, dx, dy)
            elif action == "scroll":
                delta = -float(payload.get("dy", 0))
                if abs(delta) >= 1:
                    _mouse(MOUSEEVENTF_WHEEL, data=int(max(-6, min(6, delta)) * 120))
            elif action == "tap":
                down, up = BUTTONS.get(str(payload.get("button", "left")), BUTTONS["left"])
                _mouse(down)
                _mouse(up)
            elif action == "down":
                _mouse(BUTTONS["left"][0])
            elif action == "up":
                _mouse(BUTTONS["left"][1])
            elif action == "middle":
                _mouse(BUTTONS["middle"][0])
                _mouse(BUTTONS["middle"][1])
        except Exception:
            log.debug("pointer action failed", exc_info=True)

    def page(self) -> dict:
        return {
            "blocks": [
                {
                    "type": "touchpad",
                    "label": "TOUCHPAD",
                    "sensitivity": self.settings.get("sensitivity", 1.0),
                    "hint": "Drag to move · Tap to click · Two fingers to scroll",
                }
            ]
        }
