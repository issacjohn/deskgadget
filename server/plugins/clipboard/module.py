"""Clipboard bridge: show the PC clipboard and push text to it from the phone."""
from __future__ import annotations

import ctypes
import logging

from core.base import Module as BaseModule

log = logging.getLogger("liquiddeck.clipboard")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 64-bit handles must be declared, or ctypes truncates the pointer to 32 bits
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = ctypes.c_int
user32.CloseClipboard.restype = ctypes.c_int
user32.EmptyClipboard.restype = ctypes.c_int
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_int

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _read_clipboard() -> str:
    try:
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        log.debug("clipboard read failed", exc_info=True)
        return ""


def _write_clipboard(text: str) -> bool:
    try:
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return False
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
        finally:
            user32.CloseClipboard()
    except Exception:
        log.debug("clipboard write failed", exc_info=True)
        return False


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.text = ""

    async def update(self) -> None:
        self.text = _read_clipboard()

    async def on_action(self, action: str, payload: dict) -> None:
        if action == "set_clipboard":
            text = str(payload.get("text", ""))
            if _write_clipboard(text):
                self.text = text
                await self.hub.notify("Sent to the PC clipboard")
            else:
                await self.hub.notify("Could not write the clipboard")
        elif action == "refresh":
            self.text = _read_clipboard()
            await self.hub.notify("Clipboard refreshed")
        self.push()

    def page(self) -> dict:
        text = self.text or ""
        collapsed = " ".join(text.split())
        preview = collapsed[:180] + ("…" if len(collapsed) > 180 else "")

        if not text.strip():
            head = {
                "type": "hero",
                "label": "PC CLIPBOARD",
                "value": "EMPTY",
                "unit": "",
                "sub": "Copy something on the PC, or send text below",
                "accent": self.accent,
            }
        else:
            head = {
                "type": "kv",
                "items": [
                    {"label": "LENGTH", "value": f"{len(text)} chars"},
                    {"label": "LINES", "value": str(text.count(chr(10)) + 1)},
                ],
            }

        blocks = [
            head,
            {
                "type": "list",
                "title": "ON THE PC CLIPBOARD",
                "items": [
                    {
                        "title": preview or "Empty",
                        "sub": (text.strip().splitlines() or [""])[0][:70],
                        "value": "",
                    }
                ],
            },
            {
                "type": "textinput",
                "label": "SEND TEXT TO THE PC",
                "placeholder": "Type or paste, then send",
                "button": "Copy on PC",
                "action": "set_clipboard",
            },
        ]
        return {"blocks": blocks}
