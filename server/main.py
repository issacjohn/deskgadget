"""LiquidDeck server entrypoint.

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
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import requests
from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .core.base import load_plugins
from .core.hub import Conn, Hub
from .core.web import open_url
from .core.netutil import AdbBridge, Beacon, Discovery, lan_ip
from .core.paths import dashboard_dir, plugins_dir, state_dir, templates_dir
from .core.store import Store

PORT = 8787

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("liquiddeck")

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
hub = Hub(store, {}, store.data.get("server_name", "LiquidDeck"), PORT)
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
    state_task = asyncio.create_task(_dashboard_loop(), name="dashboard-state")
    reaper_task = asyncio.create_task(_reaper_loop(), name="reaper")
    log.info("LiquidDeck ready on http://%s:%s", lan_ip(), PORT)
    log.info("dashboard  -> http://localhost:%s", PORT)
    yield
    state_task.cancel()
    reaper_task.cancel()
    for mod in hub.modules.values():
        await mod.stop()
    beacon.stop()
    adb.stop()
    discovery.stop()


app = FastAPI(title="LiquidDeck", lifespan=lifespan)


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
    store.set_theme(device_id, str(body.get("theme", "liquid")))
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
            headers={"User-Agent": "DESKGadget"},
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
                    headers={"User-Agent": "DESKGadget"},
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
        "<!doctype html><meta charset='utf-8'><title>LiquidDeck plugins</title>"
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
        headers={"Content-Disposition": 'attachment; filename="liquiddeck-module.zip"'},
    )


# --------------------------------------------------------------------------
# Dashboard UI
# --------------------------------------------------------------------------
DASHBOARD = dashboard_dir()


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse((DASHBOARD / "index.html").read_text(encoding="utf-8"))


if DASHBOARD.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD)), name="static")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
