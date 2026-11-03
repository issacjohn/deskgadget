"""One-click Windows installer.

Extracts the bundled payload into %LOCALAPPDATA%\\DESKGadget, creates Desktop and
Start Menu shortcuts, then launches the app.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

APP = "DESKGadget"


def local_app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP


def make_shortcut(link: Path, exe: Path, workdir: Path) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath='{exe}';"
        "$s.WorkingDirectory='{workdir}';"
        "$s.IconLocation='{exe}';"
        "$s.Description='DESKGadget';"
        "$s.Save()"
    ).format(link=link, exe=exe, workdir=workdir)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main() -> None:
    print()
    print("  DESKGadget setup")
    print("  ------------------------------------")

    # stop a running copy so the executable can be replaced
    subprocess.run(
        ["taskkill", "/IM", f"{APP}.exe", "/F"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    time.sleep(0.8)

    target = local_app_dir()
    target.mkdir(parents=True, exist_ok=True)

    # keep the user's devices, settings and custom modules across upgrades
    keep: dict[str, Path] = {}
    for name in ("data", "plugins"):
        src = target / name
        if src.exists():
            stash = target.parent / f".{APP}-{name}-keep"
            shutil.rmtree(stash, ignore_errors=True)
            shutil.move(str(src), str(stash))
            keep[name] = stash

    payload = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "payload.zip"
    if not payload.exists():
        print("  payload missing - build the app first")
        input("  press enter to close")
        return

    with zipfile.ZipFile(payload) as zf:
        zf.extractall(target)

    for name, stash in keep.items():
        dst = target / name
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.move(str(stash), str(dst))

    exe = target / f"{APP}.exe"
    print(f"  installed to {target}")

    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if desktop.exists():
        make_shortcut(desktop / f"{APP}.lnk", exe, target)

    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    if programs.exists():
        make_shortcut(programs / f"{APP}.lnk", exe, target)

    print("  shortcuts created")
    print("  starting DESKGadget...")
    subprocess.Popen([str(exe)], cwd=str(target))
    print()


if __name__ == "__main__":
    main()
