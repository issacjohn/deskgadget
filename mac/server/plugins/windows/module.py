"""Window switcher for macOS: every open window, tap to bring it forward.

The work happens in ``core.mac.windows`` (Accessibility API with an AppleScript
fallback). This module only keeps the phone's block shape identical to the
Windows build, so the Android app needs no changes.
"""
from __future__ import annotations

import logging

from core.base import Module as BaseModule
from core.launcher import register_icon_source
from core.mac import caps, windows

log = logging.getLogger("deskgadget.windows")


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.items: list[dict] = []
        self.message = ""

    async def update(self) -> None:
        try:
            limit = max(1, min(40, int(self.settings.get("limit", 20) or 20)))
        except Exception:
            limit = 20
        try:
            self.items = windows.list_windows(limit)
        except Exception:
            log.debug("window scan failed", exc_info=True)
            self.items = []

    async def on_action(self, action: str, payload: dict) -> None:
        if action != "focus":
            return
        key = str(payload.get("id") or payload.get("url") or "")
        target = next((window for window in self.items if window["key"] == key), None)
        app = target["app"] if target else ""
        title = target["title"] if target else ""
        ok = False
        try:
            ok = windows.focus_window(key, app, title)
        except Exception:
            log.debug("focus failed", exc_info=True)
        if ok:
            self.message = f"Focused {title or app}"
        else:
            self.message = "macOS refused the switch"
        await self.hub.notify(self.message)
        self.push()

    def _hint(self) -> str:
        permission = (caps().get("permissions") or {}).get("accessibility")
        if permission is False:
            return "Allow Accessibility for DeskGadget in the Setup card"
        return "Nothing to switch to"

    def page(self) -> dict:
        blocks: list[dict] = []
        if not self.items:
            blocks.append(
                {
                    "type": "hero",
                    "label": "OPEN WINDOWS",
                    "value": "0",
                    "unit": "",
                    "sub": self._hint(),
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
                        "id": window["key"],
                        "title": window["title"],
                        "sub": window["app"],
                        "image": (
                            f"/icons/{register_icon_source(window['path'])}"
                            if window.get("path")
                            else ""
                        ),
                        "value": "↵",
                        "action": "focus",
                    }
                    for window in self.items
                ],
            }
        )
        return {"blocks": blocks}
