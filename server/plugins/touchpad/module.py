"""Mouse & Keyboard: the phone becomes a pointer and a keyboard for the PC.

One finger moves the pointer, a tap clicks, two fingers scroll, and the
keyboard button opens a text pad that types into the focused PC window.
"""
from __future__ import annotations

import ctypes
import logging

from core.base import Module as BaseModule
from ctypes import wintypes

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


# -- keyboard --------------------------------------------------------------
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


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
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_RETURN = 0x0D
VK_BACK = 0x08
VK_TAB = 0x09
VK_ESCAPE = 0x1B


def _send(events: list[INPUT]) -> None:
    if not events:
        return
    array = (INPUT * len(events))(*events)
    ctypes.windll.user32.SendInput(len(events), array, ctypes.sizeof(INPUT))


def _key(vk: int) -> None:
    down = INPUT(type=INPUT_KEYBOARD)
    down.u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    up = INPUT(type=INPUT_KEYBOARD)
    up.u.ki = KEYBDINPUT(
        wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0
    )
    _send([down, up])


def _char(unit: int) -> None:
    down = INPUT(type=INPUT_KEYBOARD)
    down.u.ki = KEYBDINPUT(
        wVk=0, wScan=unit, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0
    )
    up = INPUT(type=INPUT_KEYBOARD)
    up.u.ki = KEYBDINPUT(
        wVk=0,
        wScan=unit,
        dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=0,
    )
    _send([down, up])


def _type_text(text: str) -> None:
    """Type arbitrary Unicode text into whichever window has focus."""
    for ch in text:
        if ch == "\n" or ch == "\r":
            _key(VK_RETURN)
        elif ch == "\b":
            _key(VK_BACK)
        elif ch == "\t":
            _key(VK_TAB)
        elif ch == "\x1b":
            _key(VK_ESCAPE)
        else:
            code = ord(ch)
            if code <= 0xFFFF:
                _char(code)
            else:
                code -= 0x10000
                _char(0xD800 + (code >> 10))
                _char(0xDC00 + (code & 0x3FF))


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
            elif action == "type":
                text = str(payload.get("text", ""))
                if text:
                    _type_text(text)
        except Exception:
            log.debug("pointer action failed", exc_info=True)

    def page(self) -> dict:
        return {
            "blocks": [
                {
                    "type": "touchpad",
                    "label": "MOUSE & KEYBOARD",
                    "sensitivity": self.settings.get("sensitivity", 1.0),
                    "hint": "Drag to move · Tap to click · Two fingers to scroll · Keyboard to type",
                }
            ]
        }
