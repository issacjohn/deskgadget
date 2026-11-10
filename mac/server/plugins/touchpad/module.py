"""Touchpad for macOS: the phone becomes a real trackpad.

Deltas arrive as floats and are accumulated, so a slow drag still moves one
pixel at a time instead of rounding to zero. Pointer injection is CGEvent
(Quartz), with ``cliclick`` as a fallback when pyobjc is not installed.
"""
from __future__ import annotations

import logging

from core.base import Module as BaseModule
from core.mac import pointer

log = logging.getLogger("deskgadget.touchpad")


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
                    pointer.move(dx, dy)
            elif action == "scroll":
                delta = -float(payload.get("dy", 0))
                if abs(delta) >= 1:
                    pointer.scroll(max(-120.0, min(120.0, delta * 6)))
            elif action == "tap":
                button = str(payload.get("button", "left"))
                pointer.click(button if button in ("left", "right", "middle") else "left")
            elif action == "down":
                pointer.press("left")
            elif action == "up":
                pointer.release("left")
            elif action == "middle":
                pointer.click("middle")
        except Exception:
            log.debug("pointer action failed", exc_info=True)

    def page(self) -> dict:
        hint = "Drag to move · Tap to click · Two fingers to scroll"
        if not pointer.available():
            hint = "Install pyobjc or cliclick to enable the touchpad"
        return {
            "blocks": [
                {
                    "type": "touchpad",
                    "label": "TOUCHPAD",
                    "sensitivity": self.settings.get("sensitivity", 1.0),
                    "hint": hint,
                }
            ]
        }
