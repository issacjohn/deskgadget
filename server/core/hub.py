"""WebSocket hub: pairing, per-device layouts, page publishing."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from .base import PROTOCOL_VERSION
from .netutil import lan_ip

log = logging.getLogger("liquiddeck.hub")


class Conn:
    def __init__(self, ws, device_id: str, name: str, info: dict[str, Any]):
        self.ws = ws
        self.device_id = device_id
        self.name = name
        self.info = info
        self.last_sent: dict[str, str] = {}
        self.connected_at = time.time()
        self.last_rx = time.time()

    async def send(self, payload: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(payload, separators=(",", ":")))

    async def send_page(self, module_id: str, page: dict[str, Any]) -> None:
        body = json.dumps(page, sort_keys=True, separators=(",", ":"))
        if self.last_sent.get(module_id) == body:
            return
        self.last_sent[module_id] = body
        await self.send(
            {
                "v": PROTOCOL_VERSION,
                "type": "page",
                "module": module_id,
                "page": page,
            }
        )


class Hub:
    def __init__(self, store, modules: dict[str, Any], server_name: str, port: int = 8787):
        self.store = store
        self.modules = modules
        self.server_name = server_name
        self.port = port
        self.conns: dict[str, list[Conn]] = {}
        self.version = "1.0.0"

    # -- device layout -----------------------------------------------------
    def enabled_for(self, device_id: str, module_id: str) -> bool:
        assign = self.store.assignments(device_id)
        if module_id in assign:
            return bool(assign[module_id].get("enabled", True))
        mod = self.modules.get(module_id)
        return bool(getattr(mod, "default_enabled", True)) and bool(getattr(mod, "enabled", True))

    def pages_for(self, device_id: str) -> list[dict[str, Any]]:
        assign = self.store.assignments(device_id)
        order: list[tuple[int, str]] = []
        for module_id, mod in self.modules.items():
            if not getattr(mod, "enabled", True):
                continue
            if not self.enabled_for(device_id, module_id):
                continue
            pos = assign.get(module_id, {}).get("position", 100)
            order.append((int(pos), module_id))
        order.sort()
        pages = []
        for _, module_id in order:
            try:
                pages.append(self.modules[module_id].render())
            except Exception:
                log.exception("render failed for %s", module_id)
        return pages

    # -- publishing --------------------------------------------------------
    def publish(self, module) -> None:
        """Called by a module from any thread/loop context."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._publish(module))

    async def _publish(self, module) -> None:
        page = module.render()
        for conns in list(self.conns.values()):
            for conn in list(conns):
                if not self.enabled_for(conn.device_id, module.id):
                    continue
                try:
                    await conn.send_page(module.id, page)
                except Exception:
                    # the socket is gone; stop counting it as online
                    self.unregister(conn)

    async def broadcast_layout(self) -> None:
        for device_id, conns in list(self.conns.items()):
            pages = self.pages_for(device_id)
            theme = (self.store.device(device_id) or {}).get("theme", "liquid")
            keep = bool((self.store.device(device_id) or {}).get("keep_screen", False))
            for conn in list(conns):
                conn.last_sent.clear()
                try:
                    await conn.send(
                        {
                            "v": PROTOCOL_VERSION,
                            "type": "layout",
                            "theme": theme,
                            "keep_screen": keep,
                            "pages": pages,
                        }
                    )
                except Exception:
                    pass

    # -- connection lifecycle ---------------------------------------------
    async def notify(self, text: str) -> None:
        for conns in list(self.conns.values()):
            for conn in list(conns):
                try:
                    await conn.send({"v": PROTOCOL_VERSION, "type": "toast", "text": text})
                except Exception:
                    pass

    async def register(self, conn: Conn) -> dict[str, Any]:
        self.conns.setdefault(conn.device_id, []).append(conn)
        token = self.store.device(conn.device_id)["token"]
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.store.touch_device(conn.device_id, now)
        log.info("device connected: %s (%s)", conn.name, conn.device_id)
        dev = self.store.device(conn.device_id) or {}
        return {
            "v": PROTOCOL_VERSION,
            "type": "welcome",
            "token": token,
            "device_id": conn.device_id,
            "server": {
                "name": self.server_name,
                "version": self.version,
                "lan_ip": lan_ip(),
                "port": self.port,
            },
            "theme": dev.get("theme", "liquid"),
            "keep_screen": bool(dev.get("keep_screen", False)),
            "pages": self.pages_for(conn.device_id),
        }

    def unregister(self, conn: Conn) -> None:
        lst = self.conns.get(conn.device_id, [])
        if conn in lst:
            lst.remove(conn)
        if not lst:
            self.conns.pop(conn.device_id, None)
        log.info("device disconnected: %s", conn.name)

    def reap_stale(self, timeout: float) -> list[Conn]:
        """Connections that stopped talking (cable pulled, Wi-Fi dropped)."""
        now = time.time()
        dead = [
            conn
            for conns in list(self.conns.values())
            for conn in list(conns)
            if now - conn.last_rx > timeout
        ]
        for conn in dead:
            self.unregister(conn)
        return dead

    # -- pairing -----------------------------------------------------------
    def pair(self, device_id: str | None, name: str, info: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        device_id = device_id or f"dev-{uuid.uuid4().hex[:10]}"
        existing = self.store.device(device_id)
        token = existing["token"] if existing else uuid.uuid4().hex
        dev = self.store.upsert_device(device_id, name, token, info)
        return dev, existing is None
