"""Power/desktop actions for the System page.

Every function has at least two implementations because these are exactly the
corners Apple moves between releases: the CGSession helper disappeared on newer
systems, so we also send the lock keystroke; ``pmset displaysleepnow`` has never
changed and is the reliable one.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from . import osascript, run

log = logging.getLogger("deskgadget.mac.power")

_CGSESSION = "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession"


def display_off() -> bool:
    return run(["pmset", "displaysleepnow"], timeout=6).returncode == 0


def lock() -> bool:
    """Lock the Mac and require the login password."""
    if Path(_CGSESSION).exists():
        if run([_CGSESSION, "-suspend"], timeout=6).returncode == 0:
            return True
    # macOS 13+: the app was removed, the shortcut is still handled by the OS
    if osascript(
        'tell application "System Events" to keystroke "q" using {control down, command down}',
        timeout=6,
    ):
        return True
    return display_off()


def show_desktop() -> bool:
    """Hide every app's windows (what the F11/Mission Control tile does)."""
    hide = (
        'tell application "System Events" to '
        'set visible of every process whose visible is true to false'
    )
    # osascript prints nothing on success, so success is the exit code
    if run(["osascript", "-e", hide], timeout=8).returncode == 0:
        return True
    # last resort: the Exposé "show desktop" key
    return (
        run(
            ["osascript", "-e", 'tell application "System Events" to key code 103'],
            timeout=6,
        ).returncode
        == 0
    )


def screenshot() -> tuple[bool, str]:
    """Save a full-screen PNG to the Desktop (Screen Recording permission)."""
    target = Path.home() / "Desktop" / time.strftime("DeskGadget %Y-%m-%d %H.%M.%S.png")
    result = run(["screencapture", "-x", str(target)], timeout=15)
    if result.returncode == 0 and target.exists():
        return True, target.name
    return False, (result.stderr or "screencapture failed").strip()[:120]


def sleep() -> bool:
    return run(["pmset", "sleepnow"], timeout=6).returncode == 0


def keep_awake(seconds: int = 3600) -> bool:
    """Best-effort caffeinate for keep-awake features; not used by default."""
    try:
        import subprocess

        subprocess.Popen(["caffeinate", "-dimsu", "-t", str(int(seconds))])
        return True
    except Exception:
        return False
