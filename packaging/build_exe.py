"""Builds the Windows artifacts.

    python packaging/build_exe.py

Outputs:
    dist/DeskGadget.exe         portable, double-click to run
    dist/DeskGadget-Setup.exe   installer: copies to %LOCALAPPDATA%, makes
                                shortcuts, launches
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_EXE = DIST / "DeskGadget.exe"
PAYLOAD = BUILD / "payload.zip"


def run(args: list[str]) -> None:
    print(" ".join(args))
    subprocess.run(args, cwd=str(ROOT), check=True)


def pyinstaller(
    name: str, entry: str, work: str, extra: list[str], *, console: bool = True
) -> None:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console" if console else "--windowed",
            "--name",
            name,
            "--icon",
            str(ROOT / "branding" / "icon.ico"),
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD / work),
            "--specpath",
            str(BUILD),
            *extra,
            entry,
        ]
    )


def main() -> None:
    (ROOT / "branding" / "icon.ico").exists() or subprocess.run(
        [sys.executable, str(ROOT / "branding" / "make_icon.py")], check=True
    )

    for cache in (ROOT / "server").rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    adb_src = ROOT / "packaging" / "vendor" / "adb"
    tools_src = ROOT / "packaging" / "tools"

    # stage only what the server needs at runtime; deliberately excludes
    # server/data (state, cached icons) and branding (screenshots)
    print("\n=== staging server ===")
    stage = BUILD / "server_bundle"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    for name in ("core", "plugins", "templates", "dashboard"):
        shutil.copytree(
            ROOT / "server" / name,
            stage / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ("main.py", "__init__.py", "PLUGINS.md"):
        src = ROOT / "server" / name
        if src.exists():
            shutil.copy2(src, stage / name)

    datas = [f"{stage}{';'}server"]
    for asset in ("icon.ico", "icon.png"):
        src = ROOT / "branding" / asset
        if src.exists():
            datas.append(f"{src}{';'}branding")
    if adb_src.exists():
        datas.append(f"{adb_src}{';'}adb")
    if tools_src.exists():
        datas.append(f"{tools_src}{';'}packaging/tools")
    uc_src = ROOT / "packaging" / "vendor" / "unitycapture"
    if uc_src.exists():
        # the DirectShow filter the server registers on first use
        datas.append(f"{uc_src}{';'}unitycapture")

    extra: list[str] = []
    for d in datas:
        extra += ["--add-data", d]
    extra += [
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "fastapi",
        "--collect-submodules",
        "zeroconf",
        "--hidden-import",
        "psutil",
        "--hidden-import",
        "requests",
        "--collect-submodules",
        "pycaw",
        "--collect-all",
        "comtypes",
        "--hidden-import",
        "pycaw",
        "--hidden-import",
        "comtypes",
        "--hidden-import",
        "server.core.paths",
        "--collect-all",
        "winrt",
        "--hidden-import",
        "winrt.windows.media.control",
        "--hidden-import",
        "winrt.windows.storage.streams",
        "--hidden-import",
        "winrt.windows.foundation",
        # the dashboard window (pywebview + WebView2 via pythonnet)
        "--collect-all",
        "webview",
        "--collect-all",
        "pythonnet",
        "--hidden-import",
        "clr",
        "--hidden-import",
        "clr_loader",
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "webview.platforms.winforms",
        # the notification-area icon
        "--collect-all",
        "pystray",
        "--hidden-import",
        "PIL.Image",
        # the virtual camera: numpy frames into the DirectShow filter
        "--collect-all",
        "pyvirtualcam",
        "--hidden-import",
        "numpy",
        "--collect-submodules",
        "numpy",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
    ]

    print("\n=== building portable app ===")
    pyinstaller(
        "DeskGadget",
        str(ROOT / "packaging" / "launcher.py"),
        "app",
        extra,
        console=False,
    )

    print("\n=== packaging payload ===")
    BUILD.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(APP_EXE, "DeskGadget.exe")
        for dll in ("UnityCaptureFilter32.dll", "UnityCaptureFilter64.dll"):
            src = uc_src / dll
            if src.exists():
                zf.write(src, f"unitycapture/{dll}")

    print("\n=== building installer ===")
    pyinstaller(
        "DeskGadget-Setup",
        str(ROOT / "packaging" / "installer.py"),
        "setup",
        ["--add-data", f"{PAYLOAD}{';'}."],
    )

    print("\nDone:")
    for f in (DIST / "DeskGadget.exe", DIST / "DeskGadget-Setup.exe"):
        if f.exists():
            print(f"  {f}  ({f.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
