"""One-click Windows installer.

Extracts the bundled payload into %LOCALAPPDATA%\\DeskGadget, creates Desktop and
Start Menu shortcuts, then launches the app.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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


def _reg_value(key: str, value: str = "") -> str:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        ) as handle:
            return str(winreg.QueryValueEx(handle, value)[0]).strip()
    except OSError:
        return ""


def register_virtual_camera(target: Path) -> None:
    """Register the camera slots once, with a single UAC prompt.

    Four slots are registered so every phone can get its own Windows camera.
    The same elevated script also grants this user write access to the slot
    names, which is what lets the server rename a slot to "DeskGadget - <phone>"
    later without another prompt.
    """
    category = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
    slots = [
        "{5C2CD55C-92AD-4999-8666-912BD3E70010}",
        "{5C2CD55C-92AD-4999-8666-912BD3E70012}",
        "{5C2CD55C-92AD-4999-8666-912BD3E70013}",
        "{5C2CD55C-92AD-4999-8666-912BD3E70014}",
    ]
    dll = target / "unitycapture" / "UnityCaptureFilter64.dll"
    dll32 = target / "unitycapture" / "UnityCaptureFilter32.dll"
    if not dll.exists():
        return

    def friendly(slot: str) -> str:
        return _reg_value(rf"CLSID\{category}\Instance\{slot}", "FriendlyName")

    current = _reg_value(r"CLSID\{5C2CD55C-92AD-4999-8666-912BD3E70010}\InprocServer32")
    ready = (
        current
        and Path(current).exists()
        and Path(current).parent.resolve() == dll.parent.resolve()
        and all(friendly(s) for s in slots)
    )
    if ready:
        print("  virtual cameras already registered")
        return

    print("  registering the virtual cameras (approve the Windows prompt)")
    lines = [
        "$ErrorActionPreference = 'SilentlyContinue'",
        f"$dll64 = '{dll}'",
        f"$dll32 = '{dll32}'",
        "$devices = '/i:UnityCaptureDevices=4'",
        "$name = '/i:UnityCaptureName=DeskGadget Camera'",
        '& regsvr32.exe /s "$dll64" "$devices" "$name"',
        'if (Test-Path $dll32) { & regsvr32.exe /s "$dll32" "$devices" "$name" }',
        r'$user = "$env:USERDOMAIN\$env:USERNAME"',
        f"$category = '{category}'",
        "$slots = @(" + ",".join(f"'{s}'" for s in slots) + ")",
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
    script_path = Path(tempfile.gettempdir()) / "deskgadget-vcam-setup.ps1"
    try:
        script_path.write_text("\r\n".join(lines), encoding="utf-8-sig")
        launcher = (
            "Start-Process -FilePath 'powershell.exe' -ArgumentList "
            f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}' "
            "-Verb RunAs -Wait -WindowStyle Hidden"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass

    current = _reg_value(r"CLSID\{5C2CD55C-92AD-4999-8666-912BD3E70010}\InprocServer32")
    if current and Path(current).parent.resolve() == dll.parent.resolve():
        print(f"  virtual cameras ready ({', '.join(friendly(s) or '?' for s in slots)})")
    else:
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
        # the filter DLLs are often loaded by a running app; never let a locked
        # file abort the upgrade
        for item in zf.infolist():
            if item.filename.lower().startswith("unitycapture/"):
                continue
            zf.extract(item, target)
        for item in zf.infolist():
            if not item.filename.lower().startswith("unitycapture/"):
                continue
            dst = target / item.filename
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(item) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
            except OSError:
                print(f"  kept the installed {Path(item.filename).name} (in use)")

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
