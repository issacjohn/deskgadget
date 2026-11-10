"""Clipboard bridge for macOS: show the Mac clipboard and push text to it.

``pbpaste``/``pbcopy`` do the work; no Accessibility or Automation permission is
involved, so this module works on every supported macOS version immediately.
"""
from __future__ import annotations

import logging

from core.base import Module as BaseModule
from core.mac import clipboard

log = logging.getLogger("deskgadget.clipboard")


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.text = ""

    async def update(self) -> None:
        self.text = clipboard.read()

    async def on_action(self, action: str, payload: dict) -> None:
        if action == "set_clipboard":
            text = str(payload.get("text", ""))
            if clipboard.write(text):
                self.text = text
                await self.hub.notify("Sent to the Mac clipboard")
            else:
                await self.hub.notify("Could not write the clipboard")
        elif action == "refresh":
            self.text = clipboard.read()
            await self.hub.notify("Clipboard refreshed")
        self.push()

    def page(self) -> dict:
        text = self.text or ""
        collapsed = " ".join(text.split())

        body = text.strip()
        if body:
            note = {
                "type": "note",
                "label": "ON THE MAC CLIPBOARD",
                "col": 0,
                "text": collapsed[:600] + ("…" if len(collapsed) > 600 else ""),
                "meta": f"{len(text)} chars · {text.count(chr(10)) + 1} lines",
            }
        else:
            note = {
                "type": "note",
                "label": "MAC CLIPBOARD",
                "col": 0,
                "text": "Nothing copied yet",
                "meta": "Copy something on the Mac, or send text across",
            }

        blocks = [
            note,
            {
                "type": "textinput",
                "label": "SEND TEXT TO THE MAC",
                "col": 1,
                "placeholder": "Type or paste, then send",
                "button": "Copy on Mac",
                "action": "set_clipboard",
            },
        ]
        return {"blocks": blocks}
