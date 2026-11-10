"""DeskGadget server entrypoint.

FastAPI app that hosts:
  * the WebSocket channel the Android client talks to  (/ws)
  * the dashboard REST API                            (/api/*)
  * the glass dashboard UI                            (/)
  * module icons for the phone                        (/icons/*)

Run:  python -m server.main     (or run.bat)
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import requests
from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .core.base import load_plugins
from .core.audio import AudioSink
from .core.hub import Conn, Hub
from .core.web import open_url
from .core.netutil import AdbBridge, Beacon, Discovery, lan_ip
from .core.paths import dashboard_dir, plugins_dir, state_dir, templates_dir
from .core.store import Store
from .core import updates, vcam

PORT = 8787

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("deskgadget")

try:  # keep a log next to the user's data so the EXE is debuggable
    from .core.paths import state_dir as _state_dir

    _fh = logging.handlers.RotatingFileHandler(
        _state_dir() / "server.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s: %(message)s"))
    logging.getLogger().addHandler(_fh)
except Exception:
    pass

BASE = Path(__file__).resolve().parent
store = Store()
hub = Hub(store, {}, store.data.get("server_name", "DeskGadget"), PORT)
hub.version = updates.current_version()
audio_sink = AudioSink()
audio_sink.state.update(
    {
        key: value
        for key, value in store.data.get("audio", {}).items()
        if key in {"enabled", "volume", "muted", "gate"}
    }
)
discovery = Discovery(PORT, hub.server_name)
beacon = Beacon(PORT, hub.server_name)
adb = AdbBridge(PORT)


def _settings_for(module_id: str):
    return store.module_settings(module_id)


def _enabled_for(module_id: str, default: bool):
    return store.module_enabled(module_id, default)


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.modules = load_plugins(hub, _settings_for, _enabled_for)
    for mod in hub.modules.values():
        if getattr(mod, "enabled", True):
            mod.start()
    discovery.start()
    beacon.start()
    adb.start()
    audio_sink.start()
    state_task = asyncio.create_task(_dashboard_loop(), name="dashboard-state")
    reaper_task = asyncio.create_task(_reaper_loop(), name="reaper")
    if vcam.is_registered():
        _start_virtual_camera()
    else:
        log.info("virtual camera not set up yet - open the camera page on the phone")
    log.info("DeskGadget ready on http://%s:%s", lan_ip(), PORT)
    log.info("dashboard  -> http://localhost:%s", PORT)
    yield
    _virtual_stop.set()
    if _virtual_thread is not None:
        _virtual_thread.join(2.0)
    state_task.cancel()
    reaper_task.cancel()
    for mod in hub.modules.values():
        await mod.stop()
    audio_sink.stop()
    beacon.stop()
    adb.stop()
    discovery.stop()


app = FastAPI(title="DeskGadget", lifespan=lifespan)


# --------------------------------------------------------------------------
# Android client channel
# --------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    conn: Conn | None = None
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=15)
        hello = json.loads(raw)
        info = hello.get("device", {})
        dev, is_new = hub.pair(
            hello.get("device_id"),
            info.get("name") or "Android device",
            info,
        )
        conn = Conn(ws, dev["id"], dev["name"], info)
        welcome = await hub.register(conn)
        welcome["new_device"] = is_new
        await conn.send(welcome)

        while True:
            msg = json.loads(await ws.receive_text())
            conn.last_rx = time.time()
            mtype = msg.get("type")
            if mtype == "ping":
                await conn.send({"v": 1, "type": "pong", "ts": msg.get("ts")})
            elif mtype == "action":
                module = hub.modules.get(msg.get("module", ""))
                if module:
                    asyncio.create_task(
                        module.on_action(msg.get("action", ""), msg.get("payload") or {})
                    )
            elif mtype == "refresh":
                for demo in hub.pages_for(conn.device_id):
                    await conn.send_page(demo["id"], demo)
            elif mtype == "open_url":
                url = str(msg.get("url", ""))
                if url.startswith(("http://", "https://")):
                    await asyncio.to_thread(open_url, url)
                    await conn.send({"v": 1, "type": "toast", "text": "Opened on the PC"})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        if conn:
            hub.unregister(conn)


# --------------------------------------------------------------------------
# Dashboard channel: pushes state instead of the browser polling /api/state
# --------------------------------------------------------------------------
dashboard_clients: set[WebSocket] = set()
_last_state_json: str | None = None


async def broadcast_state(force: bool = False) -> None:
    global _last_state_json
    if not dashboard_clients:
        return
    body = json.dumps({"type": "state", "state": await build_state()}, separators=(",", ":"))
    if not force and body == _last_state_json:
        return
    _last_state_json = body
    for client in list(dashboard_clients):
        try:
            await client.send_text(body)
        except Exception:
            dashboard_clients.discard(client)


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    dashboard_clients.add(ws)
    try:
        await ws.send_text(
            json.dumps({"type": "state", "state": await build_state()}, separators=(",", ":"))
        )
        while True:
            raw = await ws.receive_text()
            if '"ping"' in raw:
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        dashboard_clients.discard(ws)


async def _dashboard_loop() -> None:
    """Coalesced state push; only sends when something actually differs."""
    while True:
        await asyncio.sleep(1.5)
        try:
            await broadcast_state()
        except Exception:
            pass


async def _reaper_loop() -> None:
    """Drop connections whose phone vanished without a clean close."""
    while True:
        await asyncio.sleep(15)
        try:
            for conn in hub.reap_stale(75):
                try:
                    await conn.ws.close(code=1001)
                except Exception:
                    pass
            await broadcast_state()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Dashboard API
# --------------------------------------------------------------------------
def module_summary(mod) -> dict:
    settings: dict = {}
    for key, spec in (mod.settings_schema or {}).items():
        if isinstance(spec, dict) and "default" in spec:
            settings[key] = spec["default"]
    settings.update(store.module_settings(mod.id))
    return {
        "id": mod.id,
        "name": mod.name,
        "version": mod.version,
        "author": mod.author,
        "description": mod.description,
        "accent": mod.accent,
        "interval": mod.interval,
        "enabled": getattr(mod, "enabled", True),
        "settings": settings,
        "settings_schema": mod.settings_schema,
        "default_enabled": mod.default_enabled,
    }


@app.get("/api/state")
async def api_state():
    return await build_state()


async def build_state() -> dict:
    devices = []
    for dev_id, dev in store.data.get("devices", {}).items():
        assign = store.assignments(dev_id)
        items = {}
        for module_id, mod in hub.modules.items():
            item = assign.get(module_id)
            if item is None:
                item = {"enabled": mod.default_enabled and mod.enabled, "position": 100}
            items[module_id] = item
        devices.append(
            {
                **dev,
                "online": dev_id in hub.conns,
                "assignments": items,
            }
        )
    return {
        "server": {
            "name": hub.server_name,
            "version": hub.version,
            "ip": lan_ip(),
            "port": PORT,
            "usb": adb.status(),
        },
        "modules": [module_summary(m) for m in hub.modules.values()],
        "devices": devices,
    }


@app.post("/api/assignments")
async def api_assignments(req: Request):
    body = await req.json()
    device_id = body.get("device_id")
    if device_id not in store.data.get("devices", {}):
        return JSONResponse({"error": "unknown device"}, status_code=404)
    store.set_assignments(device_id, body.get("items", []))
    await hub.broadcast_layout()
    await broadcast_state()
    return {"ok": True}


@app.post("/api/devices/{device_id}/theme")
async def api_device_theme(device_id: str, req: Request):
    body = await req.json()
    store.set_theme(device_id, str(body.get("theme", "black")))
    await hub.broadcast_layout()
    await broadcast_state()
    return {"ok": True}


@app.post("/api/devices/{device_id}/screen")
async def api_device_screen(device_id: str, req: Request):
    body = await req.json()
    store.set_keep_screen(device_id, bool(body.get("enabled")))
    await hub.broadcast_layout()
    await broadcast_state()
    return {"ok": True}


@app.post("/api/modules/{module_id}/enabled")
async def api_module_enabled(module_id: str, req: Request):
    body = await req.json()
    mod = hub.modules.get(module_id)
    if not mod:
        return JSONResponse({"error": "unknown module"}, status_code=404)
    enabled = bool(body.get("enabled"))
    store.set_module_enabled(module_id, enabled)
    mod.enabled = enabled
    if enabled:
        mod.start()
    else:
        await mod.stop()
    await hub.broadcast_layout()
    await broadcast_state()
    await asyncio.sleep(0.05)
    return {"ok": True}


@app.post("/api/modules/{module_id}/settings")
async def api_module_settings(module_id: str, req: Request):
    mod = hub.modules.get(module_id)
    if not mod:
        return JSONResponse({"error": "unknown module"}, status_code=404)
    body = await req.json()
    values = dict(store.module_settings(module_id))
    values.update(body)
    store.set_module_settings(module_id, values)
    mod.settings = values
    try:
        await mod.on_settings()
    except Exception:
        log.exception("on_settings failed for %s", module_id)
    await hub.broadcast_layout()
    await broadcast_state()
    await asyncio.sleep(0.05)
    return {"ok": True, "settings": values}


@app.post("/api/devices/{device_id}/rename")
async def api_rename(device_id: str, req: Request):
    body = await req.json()
    store.rename_device(device_id, str(body.get("name", "Android device"))[:40])
    return {"ok": True}


@app.delete("/api/devices/{device_id}")
async def api_remove_device(device_id: str):
    store.remove_device(device_id)
    await hub.broadcast_layout()
    await broadcast_state()
    return {"ok": True}


@app.get("/api/apps")
async def api_apps():
    """Installed Windows apps, used by the Shortcuts editor."""
    from .core.launcher import list_installed_apps

    return {"apps": list_installed_apps()}


@app.post("/api/launch")
async def api_launch(req: Request):
    from .core.launcher import launch

    body = await req.json()
    ok, message = launch(str(body.get("path", "")))
    return {"ok": ok, "message": message}


@app.get("/artwork/{name}")
async def artwork(name: str):
    safe = Path(name).name
    path = state_dir().parent / "artwork" / safe
    if not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, headers={"Cache-Control": "max-age=86400"})


@app.get("/icons/{name}")
async def icons(name: str):
    from .core.launcher import ensure_icon

    path = ensure_icon(name)
    if not path:
        return JSONResponse({"error": "not found"}, status_code=404)
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, headers={"Cache-Control": "max-age=86400"})


# --------------------------------------------------------------------------
# Plugin management: drop in a folder or upload a zip, no restart needed
# --------------------------------------------------------------------------
async def reload_modules() -> None:
    for mod in list(hub.modules.values()):
        await mod.stop()
    hub.modules.clear()
    hub.modules.update(load_plugins(hub, _settings_for, _enabled_for))
    for mod in hub.modules.values():
        if getattr(mod, "enabled", True):
            mod.start()
    await hub.broadcast_layout()
    await broadcast_state()


@app.post("/api/modules/reload")
async def api_reload():
    await reload_modules()
    return {"ok": True, "modules": [m.id for m in hub.modules.values()]}


# --------------------------------------------------------------------------
# Module catalogue: every module this install knows about, on disk or on GitHub
# --------------------------------------------------------------------------
CATALOG_URL = "https://raw.githubusercontent.com/issacjohn/deskgadget/main/catalog.json"
PLUGIN_RAW = "https://raw.githubusercontent.com/issacjohn/deskgadget/main/server/plugins/{id}/{file}"
SAFE_ID = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


def _safe_id(module_id: str) -> str | None:
    clean = module_id.strip().lower()
    if not clean or any(ch not in SAFE_ID for ch in clean):
        return None
    return clean


def _removed_dir() -> Path:
    path = plugins_dir().parent / "plugins_removed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _catalog_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for mod in hub.modules.values():
        entries[mod.id] = {
            "id": mod.id,
            "name": mod.name,
            "version": mod.version,
            "author": mod.author,
            "description": mod.description,
            "accent": mod.accent,
        }
    for folder in _removed_dir().iterdir():
        manifest = folder / "manifest.json"
        if not folder.is_dir() or not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        mid = str(data.get("id") or folder.name)
        entries.setdefault(
            mid,
            {
                "id": mid,
                "name": data.get("name") or folder.name.title(),
                "version": data.get("version", ""),
                "author": data.get("author", ""),
                "description": data.get("description", ""),
                "accent": data.get("accent", "#7CE7FF"),
            },
        )
    return entries


@app.get("/api/catalog")
async def api_catalog():
    entries = _catalog_entries()
    installed = {m.id for m in hub.modules.values()}
    source = "bundled"
    try:
        response = await asyncio.to_thread(
            requests.get,
            CATALOG_URL,
            timeout=8,
            headers={"User-Agent": "DeskGadget"},
        )
        response.raise_for_status()
        for item in response.json().get("modules", []):
            mid = str(item.get("id", ""))
            if not mid:
                continue
            merged = dict(entries.get(mid, {}))
            merged.update(item)
            entries[mid] = merged
        source = "github"
    except Exception:
        log.info("module catalogue unreachable; showing local modules only")

    items = [
        {
            **entry,
            "installed": mid in installed,
            "removable": mid not in {"system", "media"},
        }
        for mid, entry in sorted(
            entries.items(),
            key=lambda kv: (kv[0] not in installed, str(kv[1].get("name", kv[0])).lower()),
        )
    ]
    return {"modules": items, "source": source}


@app.post("/api/modules/{module_id}/remove")
async def api_remove_module(module_id: str):
    import shutil

    mid = _safe_id(module_id)
    if not mid:
        return JSONResponse({"error": "bad id"}, status_code=400)
    src = plugins_dir() / mid
    if not src.exists():
        return JSONResponse({"error": "not installed"}, status_code=404)
    if mid in {"system", "media"}:
        return JSONResponse({"error": "core module"}, status_code=400)
    dst = _removed_dir() / mid
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.move(str(src), str(dst))
    await reload_modules()
    log.info("module removed: %s", mid)
    return {"ok": True}


@app.post("/api/modules/{module_id}/install_from_catalog")
async def api_install_from_catalog(module_id: str):
    import shutil

    mid = _safe_id(module_id)
    if not mid:
        return JSONResponse({"error": "bad id"}, status_code=400)
    if mid in hub.modules:
        return {"ok": True, "already": True}

    target = plugins_dir() / mid
    stash = _removed_dir() / mid
    if stash.exists():
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(stash), str(target))
    else:
        target.mkdir(parents=True, exist_ok=True)
        try:
            for name in ("manifest.json", "module.py"):
                url = PLUGIN_RAW.format(id=mid, file=name)
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    timeout=12,
                    headers={"User-Agent": "DeskGadget"},
                )
                response.raise_for_status()
                (target / name).write_bytes(response.content)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            return JSONResponse({"error": "download failed"}, status_code=502)

    await reload_modules()
    log.info("module installed: %s", mid)
    return {"ok": True}


@app.post("/api/modules/install")
async def api_install(file: UploadFile = File(...)):
    import shutil
    import tempfile
    import zipfile

    plugins_root = plugins_dir()
    payload = await file.read()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "plugin.zip"
            archive.write_bytes(payload)
            with zipfile.ZipFile(archive) as zf:
                for member in zf.namelist():
                    if member.startswith("/") or ".." in Path(member).parts:
                        return JSONResponse({"error": "unsafe archive"}, status_code=400)
                zf.extractall(tmp)

            def find_manifest(root: Path) -> Path | None:
                direct = root / "manifest.json"
                if direct.exists():
                    return direct
                found = [p for p in root.rglob("manifest.json") if "__MACOSX" not in p.parts]
                return found[0] if len(found) == 1 else None

            manifest = find_manifest(Path(tmp))
            if not manifest:
                return JSONResponse({"error": "manifest.json not found in zip"}, status_code=400)
            meta = json.loads(manifest.read_text(encoding="utf-8"))
            module_id = str(meta.get("id", "")).strip()
            if not module_id or not module_id.replace("-", "").replace("_", "").isalnum():
                return JSONResponse({"error": "invalid module id"}, status_code=400)
            src = manifest.parent
            dst = plugins_root / module_id
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    except zipfile.BadZipFile:
        return JSONResponse({"error": "not a zip file"}, status_code=400)

    await reload_modules()
    return {"ok": True, "id": module_id}


@app.get("/docs/plugins", response_class=HTMLResponse)
async def plugin_docs():
    from .core.paths import app_dir

    path = Path(__file__).resolve().parent / "PLUGINS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "PLUGINS.md not found"
    html = (
        "<!doctype html><meta charset='utf-8'><title>DeskGadget plugins</title>"
        "<style>body{background:#05070C;color:#E8EEF8;font:15px/1.65 system-ui;max-width:860px;"
        "margin:0 auto;padding:48px 24px}pre{background:rgba(255,255,255,.06);padding:16px;"
        "border-radius:12px;overflow:auto}code{background:rgba(255,255,255,.08);padding:2px 6px;"
        "border-radius:5px}a{color:#7CE7FF}table{border-collapse:collapse}td,th{border:1px solid #223;"
        "padding:6px 10px}</style><pre>" + text.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    )
    return HTMLResponse(html)


@app.get("/api/template")
async def api_template():
    import io
    import zipfile

    template = templates_dir() / "example-module"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in template.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(template))
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="deskgadget-module.zip"'},
    )


# --------------------------------------------------------------------------
# Phone camera frames (Camera module)
# --------------------------------------------------------------------------
_camera_lock = threading.RLock()
_camera_frames: dict[str, dict] = {}
_camera_upright: dict[str, dict] = {}

_virtual_state: dict = {"error": "", "message": "", "installed": False}

_virtual_stop = threading.Event()
_virtual_thread: threading.Thread | None = None
_vcampipes: dict[str, dict] = {}
_vcam_slots: dict[int, str] = {}
_vcam_lock = threading.RLock()
VIRTUAL_W, VIRTUAL_H, VIRTUAL_FPS = 1920, 1080, 30


def _device_key(device: str, fallback: str = "") -> str:
    name = " ".join((device or fallback or "Phone").split())
    return (name or "Phone")[:40]


_vcam_offer_lock = threading.Lock()
_vcam_offered = False


def _offer_virtual_camera() -> None:
    """The camera started without a driver: offer to install it now.

    The installer asks up front; if it was skipped, this is the second chance,
    exactly when the phone camera is actually needed.
    """
    global _vcam_offered
    with _vcam_offer_lock:
        if _vcam_offered:
            return
        _vcam_offered = True
    if vcam.is_registered():
        return

    def run() -> None:
        log.info("camera is streaming without a virtual camera; offering setup")
        ok, message = vcam.ensure()
        _virtual_state.update(installed=vcam.is_registered(), message=message)
        if ok:
            _start_virtual_camera()
            log.info("virtual camera installed on request: %s", message)
        else:
            log.warning("virtual camera setup skipped: %s", message)

    threading.Thread(target=run, name="vcam-offer", daemon=True).start()


def _store_frame(jpeg: bytes, rotation: int, device: str) -> None:
    with _camera_lock:
        _camera_frames[_device_key(device)] = {
            "jpeg": jpeg,
            "rotation": int(rotation) % 360,
            "ts": time.time(),
        }
    if not _vcam_offered:
        _offer_virtual_camera()


def _live_frames(max_age: float = 4.0) -> list[tuple[str, dict]]:
    """Newest first, one entry per phone that is still sending."""
    now = time.time()
    with _camera_lock:
        items = [
            (name, dict(info))
            for name, info in _camera_frames.items()
            if info["jpeg"] and now - info["ts"] <= max_age
        ]
    items.sort(key=lambda item: item[1]["ts"], reverse=True)
    return items


def _frame_ts(device: str | None) -> float:
    with _camera_lock:
        if device is None:
            live = _live_frames(6.0)
            return float(live[0][1]["ts"]) if live else 0.0
        return float(_camera_frames.get(device, {}).get("ts", 0.0))


def _upright_jpeg(device: str | None = None) -> bytes:
    """Rotate a frame once, then reuse it until the phone sends a new one."""
    target = device
    with _camera_lock:
        if target is None:
            live = _live_frames(6.0)
            if not live:
                return b""
            target = live[0][0]
        info = _camera_frames.get(target)
        if not info or not info["jpeg"]:
            return b""
        jpeg = info["jpeg"]
        rotation = int(info["rotation"]) % 360
        ts = float(info["ts"])
        if rotation == 0:
            return jpeg
        cached = _camera_upright.get(target)
        if cached and cached["ts"] == ts and cached["rotation"] == rotation:
            return cached["jpeg"]

    try:
        from io import BytesIO

        from PIL import Image

        image = Image.open(BytesIO(jpeg))
        image = image.rotate(-rotation, expand=True)
        out = BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=80)
        data = out.getvalue()
    except Exception:
        log.debug("could not rotate camera frame", exc_info=True)
        return jpeg

    with _camera_lock:
        _camera_upright[target] = {"jpeg": data, "ts": ts, "rotation": rotation}
    return data


def _start_virtual_camera() -> None:
    """Start the feeder thread once; the loop itself retries failures."""
    global _virtual_thread
    if _virtual_thread is not None and _virtual_thread.is_alive():
        return
    _virtual_stop.clear()
    _virtual_thread = threading.Thread(
        target=_virtual_camera_loop, name="virtual-camera", daemon=True
    )
    _virtual_thread.start()


def _frame_image(jpeg: bytes):
    """Decode a phone frame into a 1920x1080 RGB array for the filter."""
    from io import BytesIO

    import numpy as np
    from PIL import Image

    image = Image.open(BytesIO(jpeg)).convert("RGB")
    if image.size != (VIRTUAL_W, VIRTUAL_H):
        ratio = image.width / max(1, image.height)
        if abs(ratio - (VIRTUAL_W / VIRTUAL_H)) < 0.02:
            # 4:3 sources (1080p/720p/480p in portrait) scale cleanly
            image = image.resize((VIRTUAL_W, VIRTUAL_H))
        else:
            canvas = Image.new("RGB", (VIRTUAL_W, VIRTUAL_H), (6, 8, 14))
            image.thumbnail((VIRTUAL_W, VIRTUAL_H))
            canvas.paste(
                image,
                (
                    (VIRTUAL_W - image.width) // 2,
                    (VIRTUAL_H - image.height) // 2,
                ),
            )
            image = canvas
    return np.asarray(image, dtype=np.uint8)


def _open_virtual_camera(device: str) -> dict | None:
    """Claim a filter slot, name it after the phone, and open it."""
    import numpy as np
    import pyvirtualcam

    with _vcam_lock:
        slot = next((s for s, owner in _vcam_slots.items() if owner == device), None)
        if slot is None:
            slot = next((s for s in range(vcam.SLOTS) if s not in _vcam_slots), None)
            if slot is None:
                return None
            _vcam_slots[slot] = device
        taken = {entry["name"] for entry in _vcampipes.values()}

    name = vcam.phone_name(device)
    if name in taken:
        name = f"{name} #{slot + 1}"
    if not vcam.set_slot_name(slot, name):
        # no write access: keep the slot's built-in name, the feed still works
        name = vcam.slot_friendly_name(slot) or vcam.slot_name(slot)

    try:
        cam = pyvirtualcam.Camera(
            VIRTUAL_W,
            VIRTUAL_H,
            VIRTUAL_FPS,
            fmt=pyvirtualcam.PixelFormat.RGB,
            device=name,
            backend="unitycapture",
            print_fps=False,
        )
    except Exception:
        with _vcam_lock:
            _vcam_slots.pop(slot, None)
        raise

    entry = {
        "cam": cam,
        "slot": slot,
        "name": name,
        "ts": 0.0,
        "seen": time.time(),
        "last_sent": 0.0,
        "frame": np.zeros((VIRTUAL_H, VIRTUAL_W, 3), np.uint8),
    }
    with _vcam_lock:
        _vcampipes[device] = entry
    log.info("virtual camera %s <- %s", name, device)
    return entry


def _close_virtual_camera(device: str) -> None:
    with _vcam_lock:
        entry = _vcampipes.pop(device, None)
        if entry is not None:
            _vcam_slots.pop(entry["slot"], None)
    if entry is None:
        return
    try:
        entry["cam"].close()
    except Exception:
        log.debug("could not close %s", entry["name"], exc_info=True)
    try:
        vcam.set_slot_name(entry["slot"], vcam.slot_name(entry["slot"]))
    except Exception:
        log.debug("could not reset the camera name", exc_info=True)
    log.info("virtual camera released: %s", entry["name"])


def _virtual_camera_loop() -> None:
    """Feed every streaming phone into its own DirectShow camera."""
    while not _virtual_stop.is_set():
        tick = time.monotonic()
        if not vcam.is_registered():
            _virtual_state.update(error="", installed=False)
            _virtual_stop.wait(5.0)
            continue
        try:
            for device, info in _live_frames(4.0)[: vcam.SLOTS]:
                entry = _vcampipes.get(device)
                if entry is None:
                    entry = _open_virtual_camera(device)
                    if entry is None:
                        break
                fresh = False
                if info["ts"] != entry["ts"]:
                    entry["ts"] = float(info["ts"])
                    jpeg = _upright_jpeg(device)
                    if jpeg:
                        try:
                            entry["frame"] = _frame_image(jpeg)
                            fresh = True
                        except Exception:
                            log.debug("could not decode a camera frame", exc_info=True)
                    entry["seen"] = time.time()
                # keep the device alive with the last frame, but do not burn CPU
                # re-sending it at full rate while the phone is paused
                now = time.time()
                if fresh or now - entry["last_sent"] > 0.5:
                    entry["cam"].send(entry["frame"])
                    entry["last_sent"] = now
            now = time.time()
            for device in list(_vcampipes):
                entry = _vcampipes.get(device)
                if entry is not None and now - entry["seen"] > 120.0:
                    _close_virtual_camera(device)
            _virtual_state.update(error="", installed=True)
        except Exception as exc:  # numpy/pyvirtualcam missing, device busy
            _virtual_state.update(error=str(exc), installed=vcam.is_registered())
            log.warning("virtual camera unavailable: %s", exc)
            for device in list(_vcampipes):
                _close_virtual_camera(device)
            _virtual_stop.wait(4.0)
            continue
        delay = 1.0 / VIRTUAL_FPS - (time.monotonic() - tick)
        if delay > 0:
            _virtual_stop.wait(delay)
    for device in list(_vcampipes):
        _close_virtual_camera(device)


@app.websocket("/ws/camera")
async def ws_camera(ws: WebSocket):
    """Binary frames from the phone: one rotation byte, then the JPEG."""
    await ws.accept()
    device = ws.headers.get("X-Device", "") or (
        ws.client.host if ws.client else ""
    )
    try:
        while True:
            data = await ws.receive_bytes()
            if len(data) < 3 or len(data) > 3_000_000:
                continue
            jpeg = data[1:]
            if not jpeg.startswith(b"\xff\xd8"):
                continue
            _store_frame(jpeg, data[0] * 90, device)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("camera websocket closed", exc_info=True)


@app.post("/api/camera/frame")
async def api_camera_frame(request: Request):
    body = await request.body()
    if not body or len(body) > 3_000_000 or not body.startswith(b"\xff\xd8"):
        return JSONResponse({"error": "bad frame"}, status_code=400)
    rotation = request.headers.get("X-Rotation", "0")
    try:
        rotation = int(rotation)
    except ValueError:
        rotation = 0
    _store_frame(body, rotation, request.headers.get("X-Device", ""))
    return {"ok": True}


@app.get("/api/camera/latest.jpg")
async def api_camera_latest(device: str | None = None):
    jpeg = _upright_jpeg(device)
    if not jpeg:
        return JSONResponse({"error": "no frame"}, status_code=404)
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/camera/stream")
async def api_camera_stream(request: Request, device: str | None = None):
    async def frames():
        last = 0.0
        while not await request.is_disconnected():
            jpeg = _upright_jpeg(device)
            ts = _frame_ts(device)
            if jpeg and ts != last:
                last = ts
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(jpeg)).encode()
                    + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            await asyncio.sleep(0.06)

    return StreamingResponse(
        frames(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/camera/status")
async def api_camera_status():
    live = _live_frames(5.0)
    devices = [
        {
            "device": name,
            "ts": info["ts"],
            "bytes": len(info["jpeg"]),
            "rotation": info["rotation"],
        }
        for name, info in live
    ]
    if not devices:
        return {
            "live": False,
            "ts": 0.0,
            "device": "",
            "bytes": 0,
            "rotation": 0,
            "devices": [],
        }
    return {"live": True, **devices[0], "devices": devices}


def _virtual_summary() -> dict:
    with _vcam_lock:
        cams = [
            {"device": device, "slot": entry["slot"], "name": entry["name"]}
            for device, entry in _vcampipes.items()
        ]
    cams.sort(key=lambda cam: cam["slot"])
    default_name = vcam.slot_friendly_name(0) or vcam.DEVICE_NAME
    return {
        "active": bool(cams),
        "device": cams[0]["name"] if cams else default_name,
        "cameras": cams,
        "installed": vcam.is_registered(),
        "slots": vcam.SLOTS,
        "error": _virtual_state.get("error", ""),
        "message": _virtual_state.get("message", ""),
    }


@app.get("/api/camera/virtual")
async def api_camera_virtual():
    return _virtual_summary()


@app.post("/api/camera/virtual/setup")
async def api_camera_virtual_setup():
    """Register the filter slots (one UAC prompt) and start feeding frames."""
    ok, message = await asyncio.to_thread(vcam.ensure)
    _virtual_state.update(installed=vcam.is_registered(), message=message)
    if ok:
        _virtual_state.update(error="")
        _start_virtual_camera()
    return {
        "ok": ok,
        "message": message,
        "installed": vcam.is_registered(),
        "cameras": _virtual_summary()["cameras"],
    }


@app.websocket("/ws/mic")
async def ws_mic(ws: WebSocket):
    """Raw 48 kHz mono PCM16 from the phone microphone."""
    await ws.accept()
    try:
        while True:
            data = await ws.receive_bytes()
            if data and len(data) <= 1_000_000:
                audio_sink.push(data)
                _offer_virtual_mic()
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("microphone websocket closed", exc_info=True)


CABLE_RE = re.compile(
    r"cable input|vb-audio|voicemeeter|virtual cable", re.IGNORECASE
)
VB_CABLE_URL = "https://vb-audio.com/Cable/"
_mic_prompt = {"asked": False}
_mic_prompt_lock = threading.Lock()


def _virtual_mic_name(listed: list[dict] | None = None) -> str:
    for device in listed if listed is not None else audio_sink.devices():
        if CABLE_RE.search(str(device.get("name", ""))):
            return str(device["name"])
    return ""


def _audio_payload() -> dict:
    devices = audio_sink.devices()
    cable = _virtual_mic_name(devices)
    return {
        **audio_sink.snapshot(),
        "devices": devices,
        "cable": cable,
        "needs_virtual_mic": not cable,
    }


def _offer_virtual_mic() -> None:
    """Audio started with no virtual cable: point the user at VB-CABLE, once.

    The dashboard shows its own dialog while it is open; this is the fallback
    for a closed window (the app lives in the tray).
    """
    with _mic_prompt_lock:
        if _mic_prompt["asked"]:
            return
        _mic_prompt["asked"] = True

    if not audio_sink.state.get("enabled"):
        return
    if _virtual_mic_name():
        return

    def run() -> None:
        time.sleep(2.0)  # let the dashboard's websocket register first
        if dashboard_clients:
            return
        try:
            import ctypes

            answer = ctypes.windll.user32.MessageBoxW(
                None,
                "Use the phone as a microphone in Teams, Zoom or Discord?\n\n"
                "Windows needs a virtual audio device for that. Install VB-CABLE (free), "
                "then DeskGadget picks it up automatically.\n\n"
                "Open the download page now?",
                "DeskGadget",
                0x00000004 | 0x00000040 | 0x00040000,  # YESNO | INFO | TOPMOST
            )
            if answer == 6:
                open_url(VB_CABLE_URL)
        except Exception:
            log.debug("microphone prompt failed", exc_info=True)

    threading.Thread(target=run, name="mic-prompt", daemon=True).start()


@app.post("/api/camera/audio/rescan")
async def api_camera_audio_rescan():
    """Pick up a virtual cable installed while the app was running."""
    await asyncio.to_thread(audio_sink.rescan)
    return _audio_payload()


@app.get("/api/camera/audio")
async def api_camera_audio():
    return _audio_payload()


@app.post("/api/camera/audio")
async def api_camera_audio_set(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body or {}
    audio_sink.configure(
        enabled=body.get("enabled"),
        volume=body.get("volume"),
        muted=body.get("muted"),
        gate=body.get("gate"),
    )
    # remember the choice across restarts
    saved = store.data.setdefault("audio", {})
    saved.pop("device", None)
    saved.pop("monitor", None)
    for key in ("enabled", "volume", "muted", "gate"):
        if key in body:
            saved[key] = audio_sink.state.get(key)
    try:
        store.save()
    except Exception:
        log.debug("could not save audio settings", exc_info=True)
    return _audio_payload()


# --------------------------------------------------------------------------
# Desktop app updates
# --------------------------------------------------------------------------
@app.get("/api/app/update")
async def api_app_update(beta: int = 0, force: int = 0):
    return await asyncio.to_thread(updates.check, beta=bool(beta), force=bool(force))


@app.post("/api/app/update/download")
async def api_app_update_download(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    ok, message, state = await asyncio.to_thread(
        updates.download, beta=bool((body or {}).get("beta", False))
    )
    return {"ok": ok, "message": message, "progress": state}


@app.get("/api/app/update/progress")
async def api_app_update_progress():
    return updates.progress()


@app.post("/api/app/update/apply")
async def api_app_update_apply():
    """Run the downloaded installer, then hand the process over to it."""
    ok, message = await asyncio.to_thread(updates.apply)
    if ok:
        def _hand_over() -> None:
            time.sleep(1.5)  # let the response reach the dashboard
            os._exit(0)

        threading.Thread(target=_hand_over, name="update-exit", daemon=True).start()
    return {"ok": ok, "message": message}


# --------------------------------------------------------------------------
# Dashboard UI
# --------------------------------------------------------------------------
DASHBOARD = dashboard_dir()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # never let the webview keep an old dashboard after an update
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


if DASHBOARD.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD)), name="static")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
