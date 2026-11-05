"""Desktop launcher for the packaged app.

Seeds %LOCALAPPDATA%\\DESKGadget with the dashboard, plugins and templates so the
install directory stays read-only, then serves the app and opens the browser.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

APP = "DESKGadget"


def local_app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundle_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def seed_assets() -> None:
    data = local_app_dir()
    os.environ["DESKGADGET_DATA"] = str(data)

    root = bundle_root() / "server"
    removed = data / "plugins_removed"
    for name in ("plugins", "templates"):
        src_root, dst_root = root / name, data / name
        if not src_root.exists():
            continue
        dst_root.mkdir(parents=True, exist_ok=True)
        for item in src_root.iterdir():
            target = dst_root / item.name
            if target.exists():
                continue  # never clobber a module the user edited
            if name == "plugins" and (removed / item.name).exists():
                continue  # the user removed this one on purpose
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

    # dashboard ships with the build; refresh it every launch
    src, dst = root / "dashboard", data / "dashboard"
    if src.exists():
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)

    adb_dir = bundle_root() / "adb"
    if adb_dir.exists():
        os.environ["PATH"] = f"{adb_dir}{os.pathsep}" + os.environ.get("PATH", "")


def main() -> None:
    seed_assets()

    if not getattr(sys, "frozen", False):
        # dev mode: keep everything in the repo
        os.environ.pop("DESKGADGET_DATA", None)

    import uvicorn

    from server.main import PORT, app

    if "--no-browser" not in sys.argv:
        threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    print()
    print("  DESKGadget server")
    print(f"  dashboard: http://localhost:{PORT}")
    print("  press Ctrl+C to stop")
    print()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
