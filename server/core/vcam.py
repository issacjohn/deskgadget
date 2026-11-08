"""The DirectShow virtual camera (UnityCapture, MIT).

Windows apps only see a camera if a DirectShow filter is registered for the
whole machine, which needs one elevated `regsvr32` call. The filter DLLs ship
inside the bundle, but they are copied to `%LOCALAPPDATA%\\DeskGadget\\unitycapture`
first so the registration keeps pointing at a stable path when the portable EXE
is replaced.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:  # imported as `server.core.vcam` by the app, `core.vcam` by plugins
    from .paths import app_dir
except ImportError:
    from paths import app_dir

DEVICE_NAME = "Unity Video Capture"
CLSID = "{5C2CD55C-92AD-4999-8666-912BD3E70010}"
DLL32 = "UnityCaptureFilter32.dll"
DLL64 = "UnityCaptureFilter64.dll"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def bundle_dir() -> Path | None:
    """Where the DLLs are shipped: the bundle root, or the repo vendor folder."""
    for path in (
        app_dir().parent / "unitycapture",
        app_dir().parent / "packaging" / "vendor" / "unitycapture",
    ):
        if (path / DLL64).exists():
            return path
    return None


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "DeskGadget" / "unitycapture"


def registered_path() -> str:
    """The DLL Windows currently loads for this filter, or an empty string."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            rf"CLSID\{CLSID}\InprocServer32",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            return str(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return ""


def is_registered() -> bool:
    path = registered_path()
    if not path:
        return False
    dll = Path(path)
    try:
        return dll.exists() and dll.parent.resolve() == install_dir().resolve()
    except OSError:
        return False


def is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _regsvr32(dll: Path) -> None:
    if is_admin():
        subprocess.run(
            ["regsvr32", "/s", str(dll)],
            check=True,
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        return
    # one UAC prompt, then wait for regsvr32 and pass its exit code back
    script = (
        "$p = Start-Process -FilePath regsvr32.exe "
        "-ArgumentList '/s',\"{dll}\" -Verb RunAs -PassThru -Wait; "
        "exit $p.ExitCode"
    ).format(dll=dll)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )


def ensure() -> tuple[bool, str]:
    """Register the filter once. Returns (ok, message the UI can show)."""
    if is_registered():
        return True, "Virtual camera ready"
    if sys.platform != "win32":
        return False, "The virtual camera is Windows only."

    source = bundle_dir()
    if source is None:
        return False, "This build has no virtual camera files."

    target = install_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name in (DLL32, DLL64):
            src = source / name
            if not src.exists():
                continue
            dst = target / name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy2(src, dst)
    except OSError as exc:
        return False, f"Could not copy the camera driver: {exc}"

    try:
        _regsvr32(target / DLL64)
        if (target / DLL32).exists():
            _regsvr32(target / DLL32)
    except (subprocess.CalledProcessError, OSError):
        return False, "Windows blocked the camera driver (approve the prompt)."

    if not is_registered():
        return False, "Windows did not accept the camera driver."
    return True, "Virtual camera ready"
