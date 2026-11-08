"""The DirectShow virtual cameras (UnityCapture, MIT).

Windows apps only see a camera if a DirectShow filter is registered for the
whole machine, which needs one elevated setup. The filter DLLs ship inside the
bundle, but they are copied to `%LOCALAPPDATA%\\DeskGadget\\unitycapture` first
so the registration keeps pointing at a stable path when the portable EXE is
replaced.

UnityCapture exposes several device slots, each with its own CLSID and its own
shared-memory channel. We register `SLOTS` of them once, then rename a slot to
`DeskGadget - <phone>` when that phone starts streaming, so every phone shows up
as its own camera. The rename is done with plain registry writes, which works
without a prompt because setup grants the current user write access to those
keys.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # imported as `server.core.vcam` by the app, `core.vcam` by plugins
    from .paths import app_dir
except ImportError:
    from paths import app_dir

DEVICE_NAME = "DeskGadget Camera"
SLOTS = 4
CATEGORY_CLSID = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
DLL32 = "UnityCaptureFilter32.dll"
DLL64 = "UnityCaptureFilter64.dll"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- #
# naming
# --------------------------------------------------------------------------- #
def slot_clsid(slot: int) -> str:
    """UnityCapture's per-slot CLSID: 0x10, then 0x12, 0x13, 0x14, ..."""
    offset = slot + 1 if slot else 0
    return "{5C2CD55C-92AD-4999-8666-912BD3E700%02X}" % (0x10 + offset)


def slot_name(slot: int) -> str:
    """The name a slot carries before a phone claims it."""
    return DEVICE_NAME if slot == 0 else f"{DEVICE_NAME} #{slot + 1}"


def phone_name(label: str) -> str:
    """The camera name a phone gets, e.g. `DeskGadget - SM-G980F`."""
    clean = " ".join(str(label or "").split())[:40].strip(" -")
    return f"{DEVICE_NAME} - {clean}" if clean else DEVICE_NAME


# --------------------------------------------------------------------------- #
# layout
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def _read(key_path: str, value: str = "") -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            return str(winreg.QueryValueEx(key, value)[0]).strip()
    except OSError:
        return ""


def _write(key_path: str, value: str, data: str) -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT,
            key_path,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            winreg.SetValueEx(key, value, 0, winreg.REG_SZ, data)
        return True
    except OSError:
        return False


def registered_path() -> str:
    """The DLL Windows currently loads for the first slot, or an empty string."""
    return _read(rf"CLSID\{slot_clsid(0)}\InprocServer32")


def slot_friendly_name(slot: int) -> str:
    return _read(
        rf"CLSID\{CATEGORY_CLSID}\Instance\{slot_clsid(slot)}", "FriendlyName"
    )


def slot_device_path(slot: int) -> str:
    """UnityCapture registers every slot as `foo:bar`; give each one its own id.

    Apps that key on the device path (rather than the CLSID) otherwise treat the
    slots as one camera and show the same feed for all of them.
    """
    return f"foo:bar:{slot}"


def set_slot_name(slot: int, name: str) -> bool:
    """Rename a camera slot. Silently fails if setup did not grant write access."""
    instance = rf"CLSID\{CATEGORY_CLSID}\Instance\{slot_clsid(slot)}"
    ok = _write(instance, "FriendlyName", name)
    _write(instance, "DevicePath", slot_device_path(slot))
    _write(rf"CLSID\{slot_clsid(slot)}", "", name)
    return ok


def registered_slots() -> list[int]:
    return [
        slot
        for slot in range(SLOTS)
        if _read(rf"CLSID\{CATEGORY_CLSID}\Instance\{slot_clsid(slot)}", "FriendlyName")
    ]


def is_registered() -> bool:
    """True when at least the first camera slot points at our installed DLL."""
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


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #
def _setup_script(target: Path) -> str:
    """One elevated script: register the slots, then allow silent renaming."""
    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"$dll64 = '{target / DLL64}'",
        f"$dll32 = '{target / DLL32}'",
        f"$devices = '/i:UnityCaptureDevices={SLOTS}'",
        f"$name = '/i:UnityCaptureName={DEVICE_NAME}'",
        '& regsvr32.exe /s "$dll64" "$devices" "$name"',
        'if (Test-Path $dll32) { & regsvr32.exe /s "$dll32" "$devices" "$name" }',
        r'$user = "$env:USERDOMAIN\$env:USERNAME"',
        f"$category = '{CATEGORY_CLSID}'",
        "$slots = @(" + ",".join(f"'{slot_clsid(i)}'" for i in range(SLOTS)) + ")",
        "for ($i = 0; $i -lt $slots.Count; $i++) {",
        "  $s = $slots[$i]",
        "  $keys = @(",
        '    "HKLM:\\SOFTWARE\\Classes\\CLSID\\$category\\Instance\\$s",',
        '    "HKLM:\\SOFTWARE\\Classes\\CLSID\\$s"',
        "  )",
        "  foreach ($k in $keys) {",
        "    if (Test-Path $k) {",
        "      $acl = Get-Acl $k",
        "      $rule = New-Object System.Security.AccessControl.RegistryAccessRule(",
        "        $user, 'SetValue,QueryValues,EnumerateSubKeys,ReadPermissions', 'Allow')",
        "      $acl.SetAccessRule($rule)",
        "      Set-Acl $k $acl",
        "    }",
        "  }",
        '  Set-ItemProperty -ErrorAction SilentlyContinue -Path "HKLM:\\SOFTWARE\\Classes\\CLSID\\$category\\Instance\\$s" -Name DevicePath -Value "foo:bar:$i"',
        "}",
    ]
    return "\r\n".join(lines)


def _run_elevated(script: str) -> bool:
    path = Path(tempfile.gettempdir()) / f"deskgadget-vcam-{os.getpid()}.ps1"
    try:
        path.write_text(script, encoding="utf-8-sig")
    except OSError:
        return False

    launcher = (
        "Start-Process -FilePath 'powershell.exe' -ArgumentList "
        f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{path}' "
        "-Verb RunAs -Wait -WindowStyle Hidden; exit $LASTEXITCODE"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher],
            check=True,
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def ensure() -> tuple[bool, str]:
    """Register the camera slots (once). Returns (ok, message for the UI)."""
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

    if is_registered() and len(registered_slots()) >= SLOTS:
        return True, f"{SLOTS} virtual cameras ready"

    if not _run_elevated(_setup_script(target)):
        return False, "Windows blocked the camera driver (approve the prompt)."

    if not is_registered():
        return False, "Windows did not accept the camera driver."
    return True, f"{len(registered_slots())} virtual cameras ready"
