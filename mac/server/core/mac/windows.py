"""Open windows on macOS: list them and bring one forward.

Primary path is the Accessibility API (AXUIElement), which gives real window
titles and lets us raise a specific window rather than just its app. That
requires the Accessibility permission; without it we fall back to System
Events, and without that we return an empty list so the phone shows a friendly
empty state instead of an error.

The fallback paths are intentionally AppleScript-only: they work on every
macOS version this project supports, including ones where pyobjc has not
published wheels for the current Python.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from . import mainthread, osascript

log = logging.getLogger("deskgadget.mac.windows")

#: windows owned by system agents that are not useful to switch to
_SYSTEM_OWNERS = {
    "WindowManager",
    "MenuBarAgent",
    "Dock",
    "ControlCenter",
    "SystemUIServer",
    "NotificationCenter",
    "loginwindow",
    "Spotlight",
    "TextInputMenuAgent",
    "AirPlayUIAgent",
    "WeatherMenu",
}


def _quartz():
    try:
        import Quartz

        return Quartz
    except Exception:
        return None


_SCRIPT = """
try
    set out to ""
    tell application "System Events"
        set procs to every process whose background only is false
        repeat with p in procs
            set pname to name of p
            try
                repeat with w in windows of p
                    set out to out & pname & (ASCII character 9) & (name of w) & linefeed
                end repeat
            end try
        end repeat
    end tell
    return out
on error
    return ""
end try
"""


def _ax():
    try:
        import ApplicationServices as AS

        return AS
    except Exception:
        return None


def _appkit():
    try:
        import AppKit

        return AppKit
    except Exception:
        return None


def _copy(element, attribute: str):
    """AXUIElementCopyAttributeValue returns (err, value) under pyobjc."""
    AS = _ax()
    if AS is None:
        return None
    try:
        result = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None
    if isinstance(result, tuple):
        error, value = result
        return value if error == 0 else None
    return result


def _set(element, attribute: str, value) -> bool:
    AS = _ax()
    if AS is None:
        return False
    try:
        result = AS.AXUIElementSetAttributeValue(element, attribute, value)
        return result == 0 if isinstance(result, int) else True
    except Exception:
        return False


def _running_apps() -> list[dict]:
    kit = _appkit()
    if kit is None:
        return []
    try:
        workspace = kit.NSWorkspace.sharedWorkspace()
        apps = []
        for app in workspace.runningApplications():
            try:
                # 0 = regular, 1 = accessory (menu bar apps can own windows),
                # -1 = prohibited (never has a UI)
                policy = int(app.activationPolicy())
                if policy > 1:
                    continue
                name = str(app.localizedName() or "")
                if not name:
                    continue
                pid = int(app.processIdentifier())
                if pid == os.getpid():
                    continue  # never offer DeskGadget's own dashboard
                bundle = app.bundleURL()
                path = str(bundle.path()) if bundle is not None else ""
                apps.append(
                    {
                        "pid": pid,
                        "app": name,
                        "path": path,
                        "hidden": bool(app.isHidden()),
                        "accessory": policy == 1,
                    }
                )
            except Exception:
                continue
        return apps
    except Exception:
        log.debug("NSWorkspace unavailable", exc_info=True)
        return []


def _accessibility_list(limit: int) -> list[dict]:
    AS = _ax()
    if AS is None:
        return []
    items: list[dict] = []
    for app in _running_apps():
        if app["hidden"]:
            continue
        try:
            ax_app = AS.AXUIElementCreateApplication(app["pid"])
            windows = _copy(ax_app, "AXWindows") or []
        except Exception:
            continue
        for index, window in enumerate(windows):
            try:
                role = str(_copy(window, "AXRole") or "")
                if role and role not in ("AXWindow", "AXDialog", "AXSheet"):
                    continue
                title = str(_copy(window, "AXTitle") or "").strip()
                if not title:
                    title = str(_copy(window, "AXDocument") or "").strip()
                if not title:
                    title = str(_copy(window, "AXDescription") or "").strip()
                if not title:
                    # Menu bar agents own plumbing windows; real apps may own
                    # untitled panels. Only name the latter after the app.
                    if app.get("accessory"):
                        continue
                    title = f"{app['app']} window {index + 1}"
                minimized = bool(_copy(window, "AXMinimized") or False)
                items.append(
                    {
                        "key": f"{app['pid']}:{index}",
                        "pid": app["pid"],
                        "app": app["app"],
                        "title": title,
                        "path": app["path"],
                        "minimized": minimized,
                    }
                )
                if len(items) >= limit:
                    return items
            except Exception:
                continue
    return items


def _applescript_list(limit: int) -> list[dict]:
    text = osascript(_SCRIPT, timeout=10)
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        app, _, title = line.partition("\t")
        app, title = app.strip(), title.strip()
        if not app or not title:
            continue
        if (app, title) in seen:
            continue
        seen.add((app, title))
        items.append(
            {
                "key": f"{app}:{title}",
                "pid": 0,
                "app": app,
                "title": title,
                "path": "",
                "minimized": False,
            }
        )
        if len(items) >= limit:
            break
    return items


def _cg_list(limit: int) -> list[dict]:
    """Every on-screen window, with no Accessibility permission required.

    Window *titles* come from CoreGraphics and are only populated when Screen
    Recording is allowed; without it we still show one row per window named
    after its app. Focusing this row activates the app (per-window precision
    needs Accessibility).
    """
    quartz = _quartz()
    if quartz is None:
        return []
    try:
        options = (
            quartz.kCGWindowListOptionOnScreenOnly
            | quartz.kCGWindowListExcludeDesktopElements
        )
        infos = quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or []
    except Exception:
        log.debug("CGWindowList unavailable", exc_info=True)
        return []

    paths = {app["pid"]: app["path"] for app in _running_apps()}
    items: list[dict] = []
    per_app: dict[int, int] = {}
    seen: set[int] = set()

    for info in infos:
        try:
            if int(info.get("kCGWindowLayer") or 0) != 0:
                continue
            pid = int(info.get("kCGWindowOwnerPID") or 0)
            if not pid or pid == os.getpid():
                continue
            owner = str(info.get("kCGWindowOwnerName") or "").strip()
            if not owner or owner in _SYSTEM_OWNERS:
                continue
            number = int(info.get("kCGWindowNumber") or 0)
            if number in seen:
                continue
            bounds = info.get("kCGWindowBounds") or {}
            width = float(bounds.get("Width") or 0)
            height = float(bounds.get("Height") or 0)
            if width < 100 or height < 80:
                continue
            if float(info.get("kCGWindowAlpha") or 1.0) <= 0.01:
                continue

            per_app[pid] = per_app.get(pid, 0) + 1
            title = str(info.get("kCGWindowName") or "").strip()
            if not title:
                title = f"{owner} window {per_app[pid]}"
            seen.add(number)
            items.append(
                {
                    "key": f"cg:{pid}:{number}",
                    "pid": pid,
                    "app": owner,
                    "title": title,
                    "path": paths.get(pid, ""),
                    "minimized": False,
                }
            )
            if len(items) >= limit:
                break
        except Exception:
            continue
    return items


def list_windows(limit: int = 20) -> list[dict]:
    items = _accessibility_list(limit)
    if items:
        return items
    # No Accessibility permission (or no AX windows): CoreGraphics still sees
    # every on-screen window and needs no permission for owner/bounds.
    items = _cg_list(limit)
    if items:
        return items
    return _applescript_list(limit)


def _activate_app(pid: int, name: str) -> bool:
    kit = _appkit()
    if kit is not None and pid:
        try:
            for app in kit.NSWorkspace.sharedWorkspace().runningApplications():
                if int(app.processIdentifier()) != pid:
                    continue
                # 1 = NSApplicationActivateAllWindows, 2 = IgnoringOtherApps
                return bool(app.activateWithOptions_(1 | 2))
        except Exception:
            log.debug("activation failed", exc_info=True)
    return bool(osascript(f'tell application {name!r} to activate', timeout=6)) or bool(
        osascript(f'tell application "{name}" to activate', timeout=6)
    )


def focus_window(key: str, app_name: str = "", title: str = "") -> bool:
    """Raise one window. Runs on the AppKit main thread inside the bundled app."""
    if key.startswith("cg:"):
        try:
            _, pid_text, _number = key.split(":", 2)
            pid = int(pid_text)
        except ValueError:
            return False
        try:
            return bool(
                mainthread.run(
                    lambda: _activate_app(pid, app_name),
                    timeout=3.0,
                    default=False,
                )
            )
        except Exception:
            log.debug("CG focus dispatch failed", exc_info=True)
            return False

    try:
        return bool(
            mainthread.run(
                lambda: _focus_window(key, app_name, title),
                timeout=3.0,
                default=False,
            )
        )
    except Exception:
        log.debug("focus dispatch failed", exc_info=True)
        return False


def _focus_window(key: str, app_name: str = "", title: str = "") -> bool:
    """Raise one window. ``key`` is 'pid:index' from list_windows."""
    pid = 0
    index = 0
    if ":" in key:
        left, _, right = key.partition(":")
        try:
            pid = int(left)
            index = int(right)
        except ValueError:
            pid, index = 0, 0

    AS = _ax()
    if AS is not None and pid:
        try:
            ax_app = AS.AXUIElementCreateApplication(pid)
            windows = _copy(ax_app, "AXWindows") or []
            target = windows[index] if index < len(windows) else None
            if target is None and title:
                for window in windows:
                    if str(_copy(window, "AXTitle") or "").strip() == title:
                        target = window
                        break
            if target is not None:
                _set(ax_app, "AXFrontmost", True)
                if bool(_copy(target, "AXMinimized") or False):
                    _set(target, "AXMinimized", False)
                _set(target, "AXMain", True)
                _set(target, "AXFocused", True)
                try:
                    AS.AXUIElementPerformAction(target, "AXRaise")
                except Exception:
                    pass
            if _activate_app(pid, app_name):
                return True
        except Exception:
            log.debug("AX focus failed", exc_info=True)

    if app_name:
        return _activate_app(pid, app_name)
    return False
