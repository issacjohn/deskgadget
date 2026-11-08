"""One-click Windows installer.

Extracts the bundled payload into %LOCALAPPDATA%\\DeskGadget, creates Desktop and
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

APP = "DeskGadget"


def local_app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP


def force_case(path: Path) -> None:
    """NTFS is case-insensitive, so rename to make the display name match APP."""
    try:
        match = next(
            (c for c in path.parent.iterdir() if c.name.lower() == path.name.lower()),
            None,
        )
        if match and match.name != path.name:
            tmp = match.with_name(match.name + ".case-tmp")
            match.rename(tmp)
            tmp.rename(path)
    except OSError:
        pass


def drop_old_shortcut(link: Path) -> None:
    try:
        for child in link.parent.iterdir():
            if child.name.lower() == link.name.lower() and child.name != link.name:
                child.unlink()
    except OSError:
        pass


def make_shortcut(link: Path, exe: Path, workdir: Path) -> None:
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath='{exe}';"
        "$s.WorkingDirectory='{workdir}';"
        "$s.IconLocation='{exe}';"
        "$s.Description='DeskGadget';"
        "$s.Save()"
    ).format(link=link, exe=exe, workdir=workdir)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def register_virtual_camera(target: Path) -> None:
    """Register the DirectShow camera once, with a single UAC prompt."""
    import winreg

    dll = target / "unitycapture" / "UnityCaptureFilter64.dll"
    dll32 = target / "unitycapture" / "UnityCaptureFilter32.dll"
    if not dll.exists():
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            r"CLSID\{5C2CD55C-92AD-4999-8666-912BD3E70010}\InprocServer32",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            current = winreg.QueryValueEx(key, "")[0]
        if Path(current).exists() and Path(current).parent.resolve() == dll.parent.resolve():
            print("  virtual camera already registered")
            return
    except OSError:
        pass

    print("  registering the virtual camera (approve the Windows prompt)")
    for path in (dll, dll32):
        if not path.exists():
            continue
        script = (
            "$p = Start-Process -FilePath regsvr32.exe "
            "-ArgumentList '/s',\"{dll}\" -Verb RunAs -PassThru -Wait; "
            "exit $p.ExitCode"
        ).format(dll=path)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            r"CLSID\{5C2CD55C-92AD-4999-8666-912BD3E70010}\InprocServer32",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            current = str(winreg.QueryValueEx(key, "")[0])
        if Path(current).parent.resolve() == dll.parent.resolve():
            print("  virtual camera ready")
        else:
            print("  virtual camera not registered - the app can retry later")
    except OSError:
        print("  virtual camera not registered - the app can retry later")


def main() -> None:
    print()
    print("  DeskGadget setup")
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
    force_case(target)

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
    force_case(exe)
    print(f"  installed to {target}")

    register_virtual_camera(target)

    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if desktop.exists():
        drop_old_shortcut(desktop / f"{APP}.lnk")
        make_shortcut(desktop / f"{APP}.lnk", exe, target)

    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    if programs.exists():
        drop_old_shortcut(programs / f"{APP}.lnk")
        make_shortcut(programs / f"{APP}.lnk", exe, target)

    print("  shortcuts created")
    print("  starting DeskGadget...")
    subprocess.Popen([str(exe)], cwd=str(Path.home()))
    print()


if __name__ == "__main__":
    main()
