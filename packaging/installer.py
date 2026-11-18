"""One-click Windows installer.

Extracts the bundled payload into %LOCALAPPDATA%\\DeskGadget, creates Desktop and
Start Menu shortcuts, then launches the app.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
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


def install_dir() -> Path:
    """Where to install: `--dir` from the updater, else %LOCALAPPDATA%\\DeskGadget.

    The updater passes the folder of the running app so an elevated setup can
    never land in a different profile (for example when Windows asks for
    another administrator's credentials).
    """
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        if arg == "--dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if arg.startswith("--dir="):
            return Path(arg.split("=", 1)[1])
    return local_app_dir()


# --------------------------------------------------------------------------- #
# setup log and failures
# --------------------------------------------------------------------------- #
class _Tee:
    """Write status lines to the console *and* to logs/setup.log."""

    def __init__(self, *streams: object) -> None:
        self.streams = [stream for stream in streams if stream is not None]

    def write(self, text: str) -> None:
        for stream in self.streams:
            try:
                stream.write(text)  # type: ignore[union-attr]
                stream.flush()  # type: ignore[union-attr]
            except Exception:
                pass

    def flush(self) -> None:
        for stream in self.streams:
            try:
                stream.flush()  # type: ignore[union-attr]
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


def start_log() -> None:
    """Keep a log an update can be diagnosed from after the window closes."""
    try:
        folder = local_app_dir() / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        handle = open(folder / "setup.log", "a", encoding="utf-8", buffering=1)
        handle.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} DeskGadget setup ===\n")
        sys.stdout = _Tee(sys.stdout, handle)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, handle)  # type: ignore[assignment]
    except Exception:
        pass


def fail(message: str) -> None:
    print(message)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"{message}\n\nSee {local_app_dir() / 'logs' / 'setup.log'} for details.",
            "DeskGadget setup",
            0x00000010,  # MB_ICONERROR
        )
    except Exception:
        pass


def _is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_ps_script(script_path: Path) -> None:
    """Run a setup script elevated. When setup already is elevated the script
    runs directly, so Windows doesn't ask for permission a second time."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if _is_admin():
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script_path)],
            capture_output=True,
            creationflags=flags,
        )
        return
    launcher = (
        "Start-Process -FilePath 'powershell.exe' -ArgumentList "
        f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}' "
        "-Verb RunAs -Wait -WindowStyle Hidden"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", launcher],
        capture_output=True,
        creationflags=flags,
    )


# --------------------------------------------------------------------------- #
# replacing a running app
# --------------------------------------------------------------------------- #
def _image_locked(path: Path) -> bool:
    """True while Windows still has the executable mapped."""
    if not path.exists():
        return False
    try:
        with path.open("r+b"):
            return False
    except OSError:
        return True


def _kill_app() -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["taskkill", "/IM", f"{APP}.exe", "/F"],
        capture_output=True,
        creationflags=flags,
    )
    subprocess.run(
        [
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            f"Get-Process -Name '{APP}' -ErrorAction SilentlyContinue "
            "| Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        creationflags=flags,
    )


def stop_running_app(exe: Path, timeout: float = 20.0) -> None:
    """Close every copy, including one started as administrator.

    The dashboard starts setup while the app is still running, so waiting for
    a lock to clear is the normal path, not an error.
    """
    if not _image_locked(exe):
        return
    print("  closing the running DeskGadget")
    deadline = time.time() + timeout
    while time.time() < deadline:
        _kill_app()
        time.sleep(0.6)
        if not _image_locked(exe):
            return
    print("  Windows still has DeskGadget open; moving it aside")


def _set_aside(path: Path) -> Path | None:
    """A running exe cannot be overwritten, but it can be renamed."""
    stale = path.with_name(f"{path.stem}-{int(time.time())}.old{path.suffix}")
    try:
        path.rename(stale)
        return stale
    except OSError:
        return None


def _delete_later(path: Path) -> None:
    try:
        path.unlink()
        return
    except OSError:
        pass
    try:
        import ctypes

        ctypes.windll.kernel32.MoveFileExW(str(path), None, 0x4)  # delete on reboot
    except Exception:
        pass


def remove_stale(target: Path) -> None:
    for pattern in (f"{APP}-*.old.exe", "*.case-tmp"):
        for path in target.glob(pattern):
            _delete_later(path)


def _sha256_zip(zf: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with zf.open(name) as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_entry(zf: zipfile.ZipFile, item: zipfile.ZipInfo, target: Path) -> None:
    dest = target / item.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(item) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out, 1 << 20)
    try:
        stamp = time.mktime(tuple(item.date_time) + (0, 0, -1))
        os.utime(dest, (stamp, stamp))
    except (OSError, OverflowError):
        pass


def _replace_exe(zf: zipfile.ZipFile, item: zipfile.ZipInfo, target: Path) -> None:
    for _ in range(4):
        try:
            _write_entry(zf, item, target)
            return
        except OSError:
            stale = _set_aside(target / item.filename)
            if stale is not None:
                _delete_later(stale)
                time.sleep(0.4)
                continue
            time.sleep(1.0)
    raise RuntimeError(
        "Windows would not let setup replace DeskGadget.exe. "
        "Close DeskGadget and run setup again."
    )


def extract_payload(zf: zipfile.ZipFile, target: Path) -> str:
    """Write the payload, always replacing the exe; returns its sha256."""
    exe_name = f"{APP}.exe"
    exe_item = next((item for item in zf.infolist() if item.filename == exe_name), None)
    if exe_item is None:
        raise RuntimeError("the update payload has no DeskGadget.exe")
    expected = _sha256_zip(zf, exe_name)

    _replace_exe(zf, exe_item, target)

    for item in zf.infolist():
        if item is exe_item:
            continue
        try:
            _write_entry(zf, item, target)
        except OSError:
            # the filter DLLs are often loaded by a running app or explorer;
            # never let a locked file abort the upgrade
            print(f"  kept the installed {Path(item.filename).name} (in use)")
    return expected


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


def ask_for_driver() -> bool:
    """One explicit choice at install; Windows still asks for permission."""
    try:
        import ctypes

        answer = ctypes.windll.user32.MessageBoxW(
            None,
            "Install the DeskGadget Camera driver?\n\n"
            "It lets Windows apps use this phone as a webcam. "
            "Windows will ask for permission once.\n\n"
            "If you skip it, DeskGadget will offer it again when you start the camera.",
            "DeskGadget setup",
            0x00000004 | 0x00000020 | 0x00040000,  # YESNO | QUESTION | TOPMOST
        )
        return answer == 6  # IDYES
    except Exception:
        return True


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

    if not ask_for_driver():
        print("  camera driver skipped - DeskGadget will offer it when you start the camera")
        try:
            (target / "driver-declined").write_text("1", encoding="utf-8")
        except OSError:
            pass
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
        _run_ps_script(script_path)
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass

    current = _reg_value(r"CLSID\{5C2CD55C-92AD-4999-8666-912BD3E70010}\InprocServer32")
    if current and Path(current).parent.resolve() == dll.parent.resolve():
        print(f"  virtual cameras ready ({', '.join(friendly(s) or '?' for s in slots)})")
        try:
            (target / "driver-declined").unlink()
        except OSError:
            pass
    else:
        print("  virtual camera not registered - the app will offer it again")


VB_CABLE_URL = "https://vb-audio.com/Cable/"
CABLE_NAME = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"


def _has_virtual_cable() -> bool:
    """True when a VB-CABLE (or renamed) capture endpoint exists."""
    import winreg

    root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                guid = winreg.EnumKey(key, index)
                try:
                    with winreg.OpenKey(key, rf"{guid}\Properties") as props:
                        name = str(winreg.QueryValueEx(props, CABLE_NAME)[0]).lower()
                except OSError:
                    continue
                if "cable output" in name or "deskgadget audio" in name:
                    return True
    except OSError:
        pass
    return False


def install_virtual_cable(target: Path) -> None:
    """Deploy the official VB-CABLE package, with its donationware credit."""
    print("  VB-CABLE (www.vb-cable.com) is donationware by VB-Audio.")
    print("  If it is useful to you, support the project:")
    print(f"    {VB_CABLE_URL}")
    if _has_virtual_cable():
        print("  virtual audio cable already installed")
        return
    setup = target / "vbcable" / "VBCABLE_Setup_x64.exe"
    if not setup.exists():
        print("  VB-CABLE package missing from the payload")
        return

    print("  installing the virtual audio cable")
    print("  in the VB-CABLE window click Install, then close it to continue")
    if _is_admin():
        subprocess.run(
            [str(setup)],
            cwd=str(setup.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        script = (
            "$p = Start-Process -FilePath '{exe}' -WorkingDirectory '{folder}' "
            "-Verb RunAs -PassThru -Wait; exit $p.ExitCode"
        ).format(exe=setup, folder=setup.parent)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if _has_virtual_cable():
        print("  virtual audio cable ready - the phone can appear as a microphone")
    else:
        print("  virtual audio cable installed - restart Windows to finish it")


PAWNIO_URL = (
    "https://github.com/namazso/PawnIO.Setup/releases/latest/download/PawnIO_setup.exe"
)


def _pawnio_installed() -> bool:
    import winreg

    try:
        winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\PawnIO"
        ).Close()
        return True
    except OSError:
        return False


def ensure_pawnio() -> None:
    """Install PawnIO, the signed driver CPU temperatures are read through.

    LibreHardwareMonitor 0.9.x reaches the CPU's MSRs via PawnIO instead of the
    blocklisted WinRing0 driver. The official signed installer is downloaded
    from its release page, its signature is checked, and Windows asks once.
    """
    if _pawnio_installed():
        print("  temperature driver already installed")
        return
    print("  installing PawnIO (pawnio.eu) for CPU temperatures")
    import urllib.request

    target = Path(tempfile.gettempdir()) / "PawnIO_setup.exe"
    try:
        if not target.exists() or target.stat().st_size < 1_000_000:
            urllib.request.urlretrieve(PAWNIO_URL, target)
    except Exception:
        print("  could not download PawnIO - enable it from the System page instead")
        return

    print("  in the PawnIO window click Install, then close it to continue")
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$exe = '{target}'",
        "$sig = Get-AuthenticodeSignature $exe",
        "if ($sig.Status -ne 'Valid' -or "
        "$sig.SignerCertificate.Subject -notmatch 'namazso') "
        "{ throw 'PawnIO signature check failed' }",
        "Start-Process -FilePath $exe -Wait",
    ]
    script_path = Path(tempfile.gettempdir()) / "deskgadget-pawnio.ps1"
    try:
        script_path.write_text("\r\n".join(lines), encoding="utf-8-sig")
        _run_ps_script(script_path)
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass

    if _pawnio_installed():
        print("  temperature driver installed")
    else:
        print("  temperature driver not installed - enable it from the System page")


def _task_exists(name: str = "DeskGadgetSensors") -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", name],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except Exception:
        return False


def register_sensor_task(target: Path) -> None:
    """Register the elevated temperature helper, once, at logon.

    CPU package temperature needs the MSR access LibreHardwareMonitor gets only
    with administrator rights. A per-user task at highest rights reads it every
    two seconds and writes sensors.json, so the app itself stays unelevated.
    """
    exe = target / f"{APP}.exe"
    if not exe.exists() or _task_exists():
        return
    print("  enabling CPU temperature readings (approve the Windows prompt)")
    command = f'"{exe}" --sensors'
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$command = '{command}'",
        "$action = New-ScheduledTaskAction -Execute 'cmd.exe' "
        "-Argument ('/c start \"\" /min ' + $command)",
        "$trigger = New-ScheduledTaskTrigger -AtLogOn "
        "-User \"$env:USERDOMAIN\\$env:USERNAME\"",
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-ExecutionTimeLimit ([TimeSpan]::Zero)",
        "$principal = New-ScheduledTaskPrincipal "
        "-UserId \"$env:USERDOMAIN\\$env:USERNAME\" -RunLevel Highest "
        "-LogonType Interactive",
        "Register-ScheduledTask -TaskName 'DeskGadgetSensors' -Action $action "
        "-Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null",
        "Start-ScheduledTask -TaskName 'DeskGadgetSensors'",
    ]
    script_path = Path(tempfile.gettempdir()) / "deskgadget-sensors-setup.ps1"
    try:
        script_path.write_text("\r\n".join(lines), encoding="utf-8-sig")
        _run_ps_script(script_path)
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass
    if _task_exists():
        print("  CPU temperature helper registered")
    else:
        print("  CPU temperature helper skipped - enable it from the System page")


def register_startup(exe: Path) -> None:
    """Start DeskGadget at Windows login, so phones always find the server."""
    if not exe.exists():
        return
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$exe = '{exe}'",
        "$action = New-ScheduledTaskAction -Execute $exe "
        "-WorkingDirectory (Split-Path $exe)",
        "$trigger = New-ScheduledTaskTrigger -AtLogOn "
        "-User \"$env:USERDOMAIN\\$env:USERNAME\"",
        "$trigger.Delay = 'PT20S'",
        "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew",
        "$principal = New-ScheduledTaskPrincipal "
        "-UserId \"$env:USERDOMAIN\\$env:USERNAME\" -LogonType Interactive "
        "-RunLevel Limited",
        "Register-ScheduledTask -TaskName 'DeskGadget' -Action $action "
        "-Trigger $trigger -Settings $settings -Principal $principal -Force "
        "| Out-Null",
    ]
    script_path = Path(tempfile.gettempdir()) / "deskgadget-startup.ps1"
    try:
        script_path.write_text("\r\n".join(lines), encoding="utf-8-sig")
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script_path)],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        print("  starts with Windows")
    except Exception:
        print("  could not add the startup task")
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


def install() -> bool:
    target = install_dir()
    print()
    print("  DeskGadget setup")
    print("  ------------------------------------")

    target.mkdir(parents=True, exist_ok=True)
    force_case(target)
    exe = target / f"{APP}.exe"

    # Close every copy before touching the files. The dashboard update path
    # runs setup while the old app is still alive, and a copy started as
    # administrator can only be stopped by an elevated setup.
    stop_running_app(exe)
    remove_stale(target)

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
        return False

    try:
        with zipfile.ZipFile(payload) as zf:
            expected = extract_payload(zf, target)
    finally:
        for name, stash in keep.items():
            dst = target / name
            if stash.exists() and not dst.exists():
                shutil.move(str(stash), str(dst))

    force_case(exe)
    if not exe.exists() or _sha256_file(exe) != expected:
        print("  the installed DeskGadget.exe does not match the payload")
        return False

    version = ""
    try:
        version = (target / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    print(f"  installed {version or 'DeskGadget'} to {target}")

    for step in (
        lambda: register_virtual_camera(target),
        lambda: install_virtual_cable(target),
        ensure_pawnio,
        lambda: register_sensor_task(target),
    ):
        try:
            step()
        except Exception:
            traceback.print_exc()

    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    if desktop.exists():
        drop_old_shortcut(desktop / f"{APP}.lnk")
        make_shortcut(desktop / f"{APP}.lnk", exe, target)

    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    if programs.exists():
        drop_old_shortcut(programs / f"{APP}.lnk")
        make_shortcut(programs / f"{APP}.lnk", exe, target)

    print("  shortcuts created")
    register_startup(exe)
    print("  starting DeskGadget...")
    # setup runs elevated, so go through Explorer: the new app must start with
    # the user's normal token, not as administrator.
    try:
        subprocess.Popen(
            ["explorer.exe", str(exe)],
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        os.startfile(str(exe))  # type: ignore[attr-defined]
    print()
    return True


def main() -> None:
    start_log()
    try:
        ok = install()
    except Exception:
        traceback.print_exc()
        ok = False
    if not ok:
        fail("DeskGadget setup could not finish. Close DeskGadget and run setup again.")


if __name__ == "__main__":
    main()
