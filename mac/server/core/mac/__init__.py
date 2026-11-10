"""macOS integration layer for DeskGadget.

Everything that talks to macOS lives here so the rest of the server stays
portable. The rule for this package is *capability detection, never version
detection*: if AppleScript exists, use it; if CoreAudio answers, use it; if a
framework is missing, degrade to the next backend instead of raising.

Compatibility target: macOS 10.15 (Catalina) through current, Intel and Apple
Silicon, Python 3.9+. Only tools that ship with the OS are required
(``osascript``, ``pbpaste``, ``screencapture``, ``pmset``, ``open``, ``sips``).
pyobjc is optional and only unlocks the richer modules.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import importlib.util
import logging
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from ..paths import bundle_dir, bundle_dirs, is_frozen, state_dir

log = logging.getLogger("deskgadget.mac")

IS_MAC = sys.platform == "darwin"

#: subprocess flag that exists on Windows but not POSIX; keeps call sites shared
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- #
# process helpers
# --------------------------------------------------------------------------- #
def which(name: str, extra: Iterable[str] = ()) -> Optional[str]:
    """Find a CLI tool, including Homebrew and the Android SDK defaults."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in list(extra) + [
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
        f"/bin/{name}",
    ]:
        if candidate and _is_exec(candidate):
            return candidate
    return None


def _is_exec(path: str) -> bool:
    import os

    return os.path.isfile(path) and os.access(path, os.X_OK)


def run(
    argv: list[str],
    *,
    timeout: float = 8.0,
    text: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, never raise. Callers check ``returncode``."""
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=text,
            input=input_text,
            timeout=timeout,
            creationflags=NO_WINDOW,
        )
    except Exception as exc:  # missing binary, timeout, encoding
        log.debug("command failed: %s (%s)", argv[:2], exc)
        return subprocess.CompletedProcess(argv, 1, "" if text else b"", str(exc))


def output(argv: list[str], *, timeout: float = 8.0) -> str:
    result = run(argv, timeout=timeout)
    return (result.stdout or "").strip()


def osascript(script: str, *, timeout: float = 8.0) -> str:
    """Run AppleScript and return stdout, or '' when it is refused/fails.

    Automation permission is per-target-app and is prompted by macOS the first
    time. A refusal is not an error for us: the caller has a fallback.
    """
    result = run(["osascript", "-e", script], timeout=timeout)
    if result.returncode != 0:
        log.debug("osascript refused: %s", (result.stderr or "").strip()[:160])
        return ""
    return (result.stdout or "").strip()


def quote(value: str) -> str:
    """Quote a Python string for AppleScript."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# capability detection (drives the dashboard setup card)
# --------------------------------------------------------------------------- #
def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _cg_symbol(name: str):
    for path in (
        ctypes.util.find_library("CoreGraphics"),
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",
    ):
        if not path:
            continue
        try:
            lib = ctypes.CDLL(path)
            return getattr(lib, name)
        except Exception:
            continue
    return None


def accessibility_trusted() -> Optional[bool]:
    """True/False when we can ask, None when the framework is unavailable."""
    if not IS_MAC:
        return None
    try:
        import ApplicationServices as AS

        return bool(AS.AXIsProcessTrusted())
    except Exception:
        return None


def screen_recording_allowed() -> Optional[bool]:
    """CGPreflightScreenCaptureAccess exists on 10.15+; absent means unknown."""
    if not IS_MAC:
        return None
    fn = _cg_symbol("CGPreflightScreenCaptureAccess")
    if fn is None:
        return None
    try:
        fn.restype = ctypes.c_bool
        fn.argtypes = []
        return bool(fn())
    except Exception:
        return None


def automation_ok() -> Optional[bool]:
    """Cheap System Events probe. A refusal shows up as error -1743."""
    if not IS_MAC:
        return None
    result = run(["osascript", "-e", 'tell application "System Events" to count processes'], timeout=5)
    if result.returncode == 0:
        return True
    err = (result.stderr or "").lower()
    if "-1743" in err or "not authorized" in err or "not allowed" in err:
        return False
    return None


def adb_path() -> Optional[str]:
    from pathlib import Path

    candidates = []
    if is_frozen():
        for base in bundle_dirs():
            candidates.append(str(base / "bin" / "adb"))
    return which(
        "adb",
        extra=tuple(candidates)
        + (
            str(Path.home() / "Library/Android/sdk/platform-tools/adb"),
            "/opt/homebrew/share/android-commandlinetools/platform-tools/adb",
            "/usr/local/share/android-commandlinetools/platform-tools/adb",
        ),
    )


def caps(probe: bool = False) -> dict:
    """Everything the dashboard needs to explain what works and what is blocked.

    ``probe=False`` avoids asking System Events anything, so opening the
    dashboard never triggers an Automation prompt; the setup card can call
    ``/api/mac/check`` when the user asks for that test.
    """
    return {
        "platform": "mac" if IS_MAC else sys.platform,
        "macos": platform.mac_ver()[0] or platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "tools": {
            "osascript": bool(which("osascript")),
            "pbpaste": bool(which("pbpaste")),
            "screencapture": bool(which("screencapture")),
            "pmset": bool(which("pmset")),
            "sips": bool(which("sips")),
            "adb": bool(adb_path()),
        },
        "pyobjc": {
            "quartz": _has_module("Quartz"),
            "appkit": _has_module("AppKit"),
            "ax": _has_module("ApplicationServices"),
        },
        "permissions": {
            "accessibility": accessibility_trusted(),
            "screen_recording": screen_recording_allowed(),
            "automation": automation_ok() if probe else None,
        },
    }


#: dashboard pane -> System Settings anchor (macOS 13+; ignored elsewhere)
_PRIVACY_ANCHORS = {
    "accessibility": "Privacy_Accessibility",
    "screen_recording": "Privacy_ScreenCapture",
    "automation": "Privacy_Automation",
    "microphone": "Privacy_Microphone",
    "camera": "Privacy_Camera",
    "local_network": "Privacy_LocalNetwork",
    "full_disk_access": "Privacy_AllFiles",
}


def open_privacy(pane: str) -> bool:
    """Open the matching Privacy pane, falling back to System Settings itself."""
    anchor = _PRIVACY_ANCHORS.get(pane)
    urls = []
    if anchor:
        urls.append(f"x-apple.systempreferences:com.apple.preference.security?{anchor}")
    urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy")
    for url in urls:
        if run(["open", url], timeout=5).returncode == 0:
            return True
    # macOS 10.15-12: the URL scheme is less reliable, so open the app
    for app in ("System Settings", "System Preferences"):
        if run(["open", "-b", "com.apple.systempreferences"], timeout=5).returncode == 0:
            return True
    return False


# --------------------------------------------------------------------------- #
# asking macOS for permissions (the real TCC prompts)
# --------------------------------------------------------------------------- #
def request_accessibility() -> bool:
    """Show the system "control this computer" prompt, and return current trust.

    The prompt cannot grant the permission — macOS only lets the user flip the
    switch — but it names the app, offers the Settings button, and registers
    DeskGadget in the Accessibility list, which is the part people miss.
    """
    try:
        import ApplicationServices as AS

        options = {AS.kAXTrustedCheckOptionPrompt: True}
        return bool(AS.AXIsProcessTrustedWithOptions(options))
    except Exception:
        log.debug("accessibility prompt failed", exc_info=True)
        return False


def request_screen_recording() -> bool:
    """Trigger the Screen Recording prompt (macOS 10.15+)."""
    fn = _cg_symbol("CGRequestScreenCaptureAccess")
    if fn is None:
        return False
    try:
        fn.restype = ctypes.c_bool
        fn.argtypes = []
        return bool(fn())
    except Exception:
        log.debug("screen recording prompt failed", exc_info=True)
        return False


def request_automation() -> bool:
    """Prompt for Automation by sending the first Apple Event to System Events."""
    result = run(
        ["osascript", "-e", 'tell application "System Events" to count processes'],
        timeout=10,
    )
    return result.returncode == 0


def _build_fingerprint() -> str:
    """Ties the 'already asked' marker to this exact build."""
    try:
        return str(Path(sys.executable).resolve().stat().st_mtime_ns)
    except OSError:
        return "dev"


def permissions_already_requested() -> bool:
    try:
        marker = state_dir() / ".permissions-requested"
        return marker.read_text(encoding="utf-8").strip() == _build_fingerprint()
    except Exception:
        return False


def reveal_app() -> bool:
    """Show the running .app in Finder so it can be dragged into a TCC list."""
    try:
        executable = Path(sys.executable).resolve()
    except Exception:
        return False
    for parent in executable.parents:
        if parent.suffix == ".app":
            return run(["open", "-R", str(parent)], timeout=6).returncode == 0
    return run(["open", "-R", str(executable)], timeout=6).returncode == 0


def request_missing_permissions(
    force: bool = False, kinds: Optional[Iterable[str]] = None
) -> dict:
    """Ask for every missing permission once, in a sensible order.

    macOS shows one TCC dialog at a time; a short pause between requests keeps
    them from fighting. The marker means a normal launch never nags again —
    after that the dashboard card is the way back in.
    """
    wanted = {str(kind) for kind in (kinds or ("accessibility", "screen_recording", "automation"))}
    marker = state_dir() / ".permissions-requested"
    if not force and permissions_already_requested():
        return {"skipped": True, **caps()}

    results: dict = {}
    if "accessibility" in wanted and accessibility_trusted() is not True:
        results["accessibility"] = request_accessibility()
        time.sleep(0.7)
    if "screen_recording" in wanted and screen_recording_allowed() is not True:
        results["screen_recording"] = request_screen_recording()
        time.sleep(0.7)
    if "automation" in wanted:
        results["automation"] = request_automation()

    try:
        marker.write_text(_build_fingerprint(), encoding="utf-8")
    except OSError:
        log.debug("could not write the permissions marker", exc_info=True)
    return results


def notify(title: str, text: str = "") -> None:
    """A best-effort desktop notification (used when the phone is not watching)."""
    script = f"display notification {quote(text)} with title {quote(title)}"
    osascript(script, timeout=4)


from . import audio, clipboard, media, pointer, power, windows  # noqa: E402  (side-effect free)
