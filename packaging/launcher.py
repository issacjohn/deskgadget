"""DeskGadget desktop app.

Starts the server in a background thread, then shows the dashboard in its own
window using the Windows WebView2 runtime (pywebview). No console, no browser
tab: the window *is* the app. Closing the window puts DeskGadget in the
notification area so the server keeps serving phones; quit from the tray icon.

    DeskGadget.exe               the desktop app
    DeskGadget.exe --no-window   plain headless server (phones only)
    python packaging/launcher.py [--no-window]
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

APP = "DeskGadget"
APP_ID = "DeskGadget.DesktopApp"
BIND = "0.0.0.0"
PORT = 8787
URL = f"http://127.0.0.1:{PORT}/"
START_TIMEOUT = 45.0
WINDOW = {"width": 1280, "height": 830, "min": (960, 600)}

log = logging.getLogger("deskgadget.launcher")
_icon_handles: list[int] = []
_mutex_handle = None

_window = None
_tray = None
_quitting = threading.Event()
_hidden_once = False
MUTEX_NAME = "Local\\DeskGadget.Desktop"


# --------------------------------------------------------------------------- #
# layout
# --------------------------------------------------------------------------- #
def local_app_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundle_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def logs_dir() -> Path:
    path = local_app_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return logs_dir() / "server.log"


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


# --------------------------------------------------------------------------- #
# logging / dialogs
# --------------------------------------------------------------------------- #
def setup_logging() -> Path:
    """Send every log line to a file, even when there is no console."""
    path = log_path()
    try:  # keep a couple of runs, don't grow forever
        if path.exists() and path.stat().st_size > 2_000_000:
            backup = path.with_name("server.1.log")
            backup.unlink(missing_ok=True)
            path.replace(backup)
    except OSError:
        pass

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    if sys.stdout is None or sys.stderr is None:
        # --windowed build: sys.stdout/stderr are None, so point both at the
        # log file. Uvicorn and library warnings then land somewhere useful.
        try:
            stream = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            stream = open(os.devnull, "w")
        sys.stdout = sys.stderr = stream
        handler: logging.Handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        root.addHandler(handler)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(fmt)
        root.addHandler(handler)
        try:
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
        except OSError:
            pass

    return path


def show_error(message: str) -> None:
    log.error(message.replace("\n", " | "))
    try:
        ctypes.windll.user32.MessageBoxW(
            None, message, APP, 0x00000010 | 0x00040000  # MB_ICONERROR | MB_TOPMOST
        )
    except Exception:
        pass


def virtual_camera_prompt() -> None:
    """First run only: offer to register the DirectShow virtual camera.

    The installer already does this, so the prompt only reaches people running
    the portable EXE. It is asked once; reinstalling offers it again.
    """
    if not getattr(sys, "frozen", False):
        return
    marker = local_app_dir() / "virtual-camera-asked"
    if marker.exists():
        return
    try:
        from server.core import vcam
    except Exception:
        log.debug("virtual camera helper missing", exc_info=True)
        return
    if vcam.is_registered():
        return

    try:
        answer = ctypes.windll.user32.MessageBoxW(
            None,
            "Use your phone as a camera in Windows apps?\n\n"
            "DeskGadget installs a virtual camera called \"Unity Video Capture\". "
            "Windows asks for permission once.\n\n"
            "You can still send the camera feed to the dashboard without it.",
            APP,
            0x00000004 | 0x00000040 | 0x00040000,  # MB_YESNO | INFO | TOPMOST
        )
    except Exception:
        return

    if answer == 6:  # IDYES
        try:
            ok, message = vcam.ensure()
            log.info("virtual camera setup: %s", message)
            if not ok:
                show_error(message)
        except Exception:
            log.exception("virtual camera setup failed")
    try:
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# server
# --------------------------------------------------------------------------- #
def port_open(port: int = PORT) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def desk_gadget_state() -> dict | None:
    """Return /api/state when a DeskGadget server already owns the port."""
    try:
        import requests

        response = requests.get(f"http://127.0.0.1:{PORT}/api/state", timeout=2.0)
        if response.status_code != 200:
            return None
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get("server"), dict) and "modules" in data:
            return data
    except Exception:
        return None
    return None


class Server(threading.Thread):
    """Uvicorn in a thread so the window owns the main thread."""

    def __init__(self) -> None:
        super().__init__(name="deskgadget-server", daemon=True)
        self.server = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            import uvicorn

            from server.main import app

            config = uvicorn.Config(
                app,
                host=BIND,
                port=PORT,
                log_level="info",
                access_log=False,
                log_config=None,  # keep our root logger / log file
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except BaseException as exc:  # noqa: BLE001 - reported to the user
            self.error = exc
            log.exception("the server failed to start")

    def stop(self, timeout: float = 8.0) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.is_alive():
            self.join(timeout)


def wait_ready(server: Server, timeout: float = START_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.error is not None:
            return False
        if desk_gadget_state() is not None:
            return True
        time.sleep(0.2)
    return False


# --------------------------------------------------------------------------- #
# window
# --------------------------------------------------------------------------- #
def window_state_path() -> Path:
    return local_app_dir() / "window.json"


def initial_geometry() -> dict[str, int]:
    geometry = {
        "width": WINDOW["width"],
        "height": WINDOW["height"],
    }
    try:
        saved = json.loads(window_state_path().read_text("utf-8"))
        width, height = int(saved["width"]), int(saved["height"])
        x, y = int(saved["x"]), int(saved["y"])
    except Exception:
        return geometry

    if width < WINDOW["min"][0] or height < WINDOW["min"][1]:
        return geometry
    # keep it on a monitor even if the desk layout changed
    try:
        user32 = ctypes.windll.user32
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if vx <= x <= vx + vw - 120 and vy <= y <= vy + vh - 120:
            geometry.update(x=x, y=y)
    except Exception:
        pass
    geometry.update(width=width, height=height)
    return geometry


def save_geometry(window) -> None:
    try:
        data = {
            "width": int(window.width),
            "height": int(window.height),
            "x": int(window.x),
            "y": int(window.y),
        }
        window_state_path().write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        log.debug("could not remember the window position", exc_info=True)


def set_app_user_model_id() -> None:
    """Own taskbar identity, so Windows shows our icon instead of python.exe's."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        log.debug("could not set the app id", exc_info=True)


def _find_window(title: str) -> int:
    user32 = ctypes.windll.user32
    pid = os.getpid()
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value != title:
            return True
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else 0


def _load_icon(path: Path, width: int, height: int) -> int:
    try:
        return int(
            ctypes.windll.user32.LoadImageW(
                None, str(path), 1, width, height, 0x00000010  # IMAGE_ICON, LR_LOADFROMFILE
            )
        )
    except Exception:
        return 0


def apply_window_icon(title: str, path: Path) -> None:
    """Put the DeskGadget icon on the title bar, Alt-Tab and the taskbar.

    WinForms already sets the form icon, but a process launched as python.exe
    keeps Python's icon in the taskbar until the window icon is forced.
    """
    if not path.exists():
        return
    user32 = ctypes.windll.user32
    for _ in range(20):
        hwnd = _find_window(title)
        if hwnd:
            break
        time.sleep(0.15)
    else:
        log.debug("window handle not found, icon not applied")
        return

    small = _load_icon(path, user32.GetSystemMetrics(49), user32.GetSystemMetrics(50))
    big = _load_icon(path, user32.GetSystemMetrics(11), user32.GetSystemMetrics(12))
    if small:
        user32.SendMessageW(hwnd, 0x0080, 0, small)  # WM_SETICON, ICON_SMALL
        user32.SendMessageW(hwnd, 0x0080, 2, small)  # WM_SETICON, ICON_SMALL2
        _icon_handles.append(small)
    if big:
        user32.SendMessageW(hwnd, 0x0080, 1, big)  # WM_SETICON, ICON_BIG
        _icon_handles.append(big)
    log.info("window icon applied")


def open_window(url: str) -> bool:
    """Show the dashboard in a native WebView2 window."""
    global _window
    try:
        import webview
    except Exception:
        log.exception("pywebview is not available")
        return False

    try:
        icon = bundle_root() / "branding" / "icon.ico"
        _window = webview.create_window(
            APP,
            url,
            **initial_geometry(),
            min_size=WINDOW["min"],
            background_color="#05070C",
            text_select=True,
        )
        if _window is None:
            return False
        _window.events.closing += _on_closing
        _window.events.loaded += lambda: (apply_window_icon(APP, icon), start_tray())
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(local_app_dir() / "webview"),
            icon=str(icon) if icon.exists() else None,
        )
        stop_tray()
        return True
    except Exception:
        log.exception("the native window could not open")
        return False


# --------------------------------------------------------------------------- #
# notification area
# --------------------------------------------------------------------------- #
def _tray_image(path: Path):
    from PIL import Image

    image = Image.open(path)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.resize((64, 64), Image.LANCZOS)


def _show_window(icon=None, item=None) -> None:
    try:
        if _window is not None:
            _window.show()
    except Exception:
        log.exception("could not show the window")


def _open_data_folder(icon=None, item=None) -> None:
    try:
        os.startfile(str(local_app_dir()))  # type: ignore[attr-defined]
    except Exception:
        log.exception("could not open the data folder")


def _quit_from_tray(icon=None, item=None) -> None:
    log.info("quit from the tray")
    _quitting.set()
    stop_tray()
    try:
        if _window is not None:
            _window.destroy()
    except Exception:
        log.exception("could not destroy the window")


def stop_tray() -> None:
    global _tray
    tray, _tray = _tray, None
    if tray is None:
        return
    try:
        tray.stop()
    except Exception:
        log.debug("tray icon already stopped", exc_info=True)


def start_tray() -> None:
    """A notification-area icon, so a closed window keeps serving phones."""
    global _tray
    if _tray is not None:
        return
    try:
        import pystray
        from pystray import Menu, MenuItem

        icon_dir = bundle_root() / "branding"
        png, ico = icon_dir / "icon.png", icon_dir / "icon.ico"
        image = _tray_image(png if png.exists() else ico)
        menu = Menu(
            MenuItem("Open dashboard", _show_window, default=True),
            MenuItem("Open data folder", _open_data_folder),
            Menu.SEPARATOR,
            MenuItem("Quit DeskGadget", _quit_from_tray),
        )
        _tray = pystray.Icon(APP_ID, image, f"{APP} — running", menu)
        threading.Thread(target=_tray.run, name="deskgadget-tray", daemon=True).start()
        log.info("tray icon ready")
    except Exception:
        log.exception("could not create the tray icon")


def _on_closing() -> bool:
    """Closing the window hides it to the notification area, it does not quit."""
    global _hidden_once
    try:
        save_geometry(_window)
    except Exception:
        pass
    if _quitting.is_set():
        return True
    if _tray is None:
        # no notification-area icon to come back from: quit instead of vanishing
        log.warning("no tray icon, closing the app")
        return True
    try:
        _window.hide()
    except Exception:
        log.exception("could not hide the window")
        return True
    if _tray is not None and not _hidden_once:
        _hidden_once = True
        try:
            _tray.notify(
                "DeskGadget is still running. Click the tray icon to open the dashboard again.",
                APP,
            )
        except Exception:
            pass
    return False


def open_edge_app(url: str) -> subprocess.Popen | None:
    """Fallback when WebView2 is missing: a chromeless Edge app window."""
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    ]
    for exe in candidates:
        if not exe.exists():
            continue
        try:
            return subprocess.Popen(
                [str(exe), f"--app={url}", "--no-first-run", "--start-maximized"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.exception("Edge app mode failed")
    return None


def show_dashboard(url: str) -> bool:
    if open_window(url):
        return True

    log.warning("falling back to an Edge app window")
    proc = open_edge_app(url)
    if proc is not None:
        # the Edge window is the app now: keep the server alive until it closes
        try:
            proc.wait()
        except KeyboardInterrupt:
            pass
        return True

    log.warning("falling back to the default browser")
    try:
        opened = bool(webbrowser.open(url))
    except Exception:
        opened = False
    if opened:
        # no window of ours to close, so the dialog doubles as the quit button
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "The DeskGadget dashboard is open in your browser.\n\n"
                "Click OK to stop the server.",
                APP,
                0x00000040 | 0x00040000,  # MB_ICONINFORMATION | MB_TOPMOST
            )
        except Exception:
            pass
        return True

    show_error(
        "DeskGadget could not open its window.\n\n"
        "Install the Microsoft Edge WebView2 runtime, then start DeskGadget again.\n\n"
        f"You can still use the dashboard at {url}"
    )
    return False


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def _headless() -> None:
    import uvicorn

    from server.main import app

    log.info("DeskGadget server (headless) on http://localhost:%s", PORT)
    uvicorn.run(app, host=BIND, port=PORT, log_level="info", access_log=False)


def focus_existing_window() -> bool:
    """Bring the window of an already-running DeskGadget to the front."""
    user32 = ctypes.windll.user32
    for _ in range(10):
        hwnd = user32.FindWindowW(None, APP)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
        time.sleep(0.2)
    return False


def claim_single_instance() -> bool:
    """False when another DeskGadget process already holds the mutex."""
    global _mutex_handle
    try:
        kernel32 = ctypes.windll.kernel32
        _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def main() -> int:
    headless = any(arg in sys.argv[1:] for arg in ("--no-window", "--no-browser", "-n"))
    # pywebview stores the app root from argv[0] when imported; make it absolute
    # before changing the working directory, or dev mode looks in the wrong place.
    try:
        sys.argv[0] = str(Path(sys.argv[0]).resolve())
    except Exception:
        pass
    path = setup_logging()
    os.environ.setdefault("PYTHONUTF8", "1")
    if str(bundle_root()) not in sys.path:
        sys.path.insert(0, str(bundle_root()))

    seed_assets()

    # Never run from the install directory: children (adb, browsers) inherit the
    # cwd and keep a handle on the folder, which blocks case-only renames.
    try:
        os.chdir(Path.home())
    except OSError:
        pass

    if not getattr(sys, "frozen", False):
        # dev mode: keep everything in the repo
        os.environ.pop("DESKGADGET_DATA", None)

    log.info(
        "%s starting (frozen=%s, log=%s)",
        APP,
        bool(getattr(sys, "frozen", False)),
        path,
    )

    if headless:
        _headless()
        return 0

    virtual_camera_prompt()
    set_app_user_model_id()

    if not claim_single_instance():
        log.info("another DeskGadget is running; bringing its window forward")
        if focus_existing_window():
            return 0
        log.info("no open window to focus; opening one against the running server")

    owned = False
    server = Server()
    try:
        state = desk_gadget_state()
        if state is not None:
            name = state.get("server", {}).get("name") or APP
            log.info("%s is already running on port %s; opening its dashboard", name, PORT)
        elif port_open():
            show_error(
                f"Port {PORT} is already in use by another app.\n\n"
                "Close that app (or stop the other DeskGadget server), then try again."
            )
            return 1
        else:
            server.start()
            owned = True
            if not wait_ready(server):
                detail = f"\n\n{server.error}" if server.error else ""
                show_error(
                    "DeskGadget could not start its server."
                    f"{detail}\n\nSee the log: {path}"
                )
                return 1
            log.info("server ready on http://localhost:%s", PORT)

        if not show_dashboard(URL):
            return 1
        log.info("window closed")
        return 0
    finally:
        stop_tray()
        if owned:
            log.info("stopping the server")
            server.stop()
        logging.shutdown()


if __name__ == "__main__":
    code = 0
    try:
        code = main()
    except BaseException:
        log.exception("fatal error")
        try:
            show_error(f"DeskGadget hit an unexpected error.\n\n{traceback.format_exc(limit=4)}")
        except Exception:
            pass
        code = 1
    # WebView2 / pythonnet can leave non-daemon threads behind. The window is
    # closed and the server is stopped by now, so end the process for real.
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        os._exit(code)
    sys.exit(code)
