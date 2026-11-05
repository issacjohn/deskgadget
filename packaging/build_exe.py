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


def pyinstaller(name: str, entry: str, work: str, extra: list[str]) -> None:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
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
    if adb_src.exists():
        datas.append(f"{adb_src}{';'}adb")
    if tools_src.exists():
        datas.append(f"{tools_src}{';'}packaging/tools")

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
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "numpy",
    ]

    print("\n=== building portable app ===")
    pyinstaller("DeskGadget", str(ROOT / "packaging" / "launcher.py"), "app", extra)

    print("\n=== packaging payload ===")
    BUILD.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(APP_EXE, "DeskGadget.exe")

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
