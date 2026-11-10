"""Pointer injection for the touchpad module.

Quartz CGEvent is the supported way to move a cursor from a background process
and behaves the same on Intel and Apple Silicon. If pyobjc is not installed we
fall back to ``cliclick`` (a 200 KB CLI) and otherwise report that touchpad is
unavailable instead of failing silently.
"""
from __future__ import annotations

import logging
from typing import Optional

from . import which

log = logging.getLogger("deskgadget.mac.pointer")

_BUTTONS = {
    "left": ("kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGMouseButtonLeft"),
    "right": ("kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGMouseButtonRight"),
    "middle": ("kCGEventOtherMouseDown", "kCGEventOtherMouseUp", "kCGMouseButtonCenter"),
}


def _quartz():
    try:
        import Quartz  # pyobjc-framework-Quartz

        return Quartz
    except Exception:
        return None


def _cliclick() -> Optional[str]:
    return which("cliclick")


def available() -> bool:
    return _quartz() is not None or _cliclick() is not None


def _location(q):
    event = q.CGEventCreate(None)
    point = q.CGEventGetLocation(event)
    return float(point.x), float(point.y)


def move(dx: int, dy: int) -> bool:
    dx, dy = int(dx), int(dy)
    if not dx and not dy:
        return True
    q = _quartz()
    if q is not None:
        try:
            x, y = _location(q)
            event = q.CGEventCreateMouseEvent(
                None, q.kCGEventMouseMoved, (x + dx, y + dy), q.kCGMouseButtonLeft
            )
            q.CGEventPost(q.kCGHIDEventTap, event)
            return True
        except Exception:
            log.debug("quartz move failed", exc_info=True)
    tool = _cliclick()
    if tool:
        from . import run

        return run([tool, f"m:+{dx},+{dy}"], timeout=4).returncode == 0
    return False


def _post(button: str, down: bool) -> bool:
    q = _quartz()
    if q is None:
        return False
    down_name, up_name, button_name = _BUTTONS.get(button, _BUTTONS["left"])
    try:
        x, y = _location(q)
        kind = getattr(q, down_name if down else up_name)
        btype = getattr(q, button_name)
        event = q.CGEventCreateMouseEvent(None, kind, (x, y), btype)
        q.CGEventPost(q.kCGHIDEventTap, event)
        return True
    except Exception:
        log.debug("quartz button failed", exc_info=True)
        return False


def click(button: str = "left") -> bool:
    q = _quartz()
    if q is not None:
        return _post(button, True) and _post(button, False)
    tool = _cliclick()
    if tool:
        from . import run

        code = {"left": "c", "right": "rc", "middle": None}.get(button)
        if code:
            return run([tool, code + ":."], timeout=4).returncode == 0
    return False


def press(button: str = "left") -> bool:
    return _post(button, True)


def release(button: str = "left") -> bool:
    return _post(button, False)


def scroll(dy: float) -> bool:
    """Scroll a number of pixels; positive is up, matching the phone's gesture."""
    q = _quartz()
    if q is not None:
        try:
            event = q.CGEventCreateScrollWheelEvent(
                None, q.kCGScrollEventUnitPixel, 1, int(dy)
            )
            q.CGEventPost(q.kCGHIDEventTap, event)
            return True
        except Exception:
            log.debug("quartz scroll failed", exc_info=True)
    tool = _cliclick()
    if tool and abs(dy) >= 1:
        from . import run

        return run([tool, f"w:{int(dy) * 20}"], timeout=4).returncode == 0
    return False
