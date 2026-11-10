"""Filesystem layout for the macOS build.

Two modes:

* **Source** — data stays in ``server/`` (plugins, dashboard, state), so a
  checkout is self-contained and easy to inspect.
* **Bundled app** — the code and assets are read-only inside
  ``DeskGadget.app`` (``sys._MEIPASS``), while mutable state lives in
  ``~/Library/Application Support/DeskGadget``. ``core.seed`` copies the
  bundled plugins/dashboard there on first run and after an update.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_frozen() -> bool:
    """True inside a PyInstaller bundle (the standalone .app)."""
    return bool(getattr(sys, "frozen", False))


def bundle_dirs() -> list[Path]:
    """Candidate roots inside a frozen bundle, most specific first.

    PyInstaller 6 stores data in ``Contents/Resources`` and shared libraries in
    ``Contents/Frameworks``; earlier versions used ``Contents/MacOS``. Searching
    the siblings keeps the app working across all of them.
    """
    if not is_frozen():
        return [Path(os.environ.get("DESKGADGET_ROOT") or export_root())]
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    executable = Path(sys.executable).resolve()
    candidates = [
        base,
        base.parent / "Resources",
        base.parent / "Frameworks",
        executable.parent.parent / "Resources",
        executable.parent,
    ]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def export_root() -> Path:
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """Read-only root that actually contains the bundled assets."""
    candidates = bundle_dirs()
    for candidate in candidates:
        if (candidate / "dashboard").is_dir() or (candidate / "plugins").is_dir():
            return candidate
    for candidate in candidates:
        if (candidate / "VERSION").exists():
            return candidate
    return candidates[0]


def default_user_data() -> Path:
    """Where a packaged install keeps state on each platform."""
    if is_mac():
        return Path.home() / "Library" / "Application Support" / "DeskGadget"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DeskGadget"
    return Path.home() / ".local" / "share" / "deskgadget"


def app_dir() -> Path:
    return Path(os.environ.get("DESKGADGET_ROOT") or bundle_dir())


def data_dir() -> Path:
    explicit = os.environ.get("DESKGADGET_DATA")
    if explicit:
        return Path(explicit)
    if is_frozen():
        return default_user_data()
    return app_dir()


def plugins_dir() -> Path:
    return data_dir() / "plugins"


def dashboard_dir() -> Path:
    return data_dir() / "dashboard"


def templates_dir() -> Path:
    return data_dir() / "templates"


def state_dir() -> Path:
    path = data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    if is_mac():
        path = Path.home() / "Library" / "Logs"
    else:
        path = state_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = state_dir()
    return path
