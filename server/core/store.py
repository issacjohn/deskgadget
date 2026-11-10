"""Tiny JSON-file state store: paired devices, assignments, module settings."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..core.paths import state_dir

DATA_DIR = state_dir()
STATE_FILE = DATA_DIR / "state.json"


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "server_name": "DeskGadget",
            "devices": {},
            "module_settings": {},
            "module_enabled": {},
            "assignments": {},
        }
        if STATE_FILE.exists():
            try:
                loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except Exception:
                pass
        # the product was renamed; migrate the old default name
        if self.data.get("server_name") in (None, "", "DeskGadget"):
            self.data["server_name"] = "DeskGadget"
        self.save()

    def save(self) -> None:
        with self._lock:
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp.replace(STATE_FILE)

    # -- modules -----------------------------------------------------------
    def module_settings(self, module_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self.data["module_settings"].get(module_id, {}))

    def set_module_settings(self, module_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            self.data["module_settings"][module_id] = values
            self.save()

    def module_enabled(self, module_id: str, default: bool = True) -> bool:
        with self._lock:
            return bool(self.data["module_enabled"].get(module_id, default))

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        with self._lock:
            self.data["module_enabled"][module_id] = bool(enabled)
            self.save()

    # -- devices -----------------------------------------------------------
    def device(self, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self.data["devices"].get(device_id)

    def upsert_device(self, device_id: str, name: str, token: str, info: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            dev = self.data["devices"].get(device_id) or {}
            dev.update(
                {
                    "id": device_id,
                    "name": dev.get("name") or name or "Android device",
                    "token": token,
                    "info": info,
                    "theme": dev.get("theme") or self.data.get("theme") or "black",
                    "keep_screen": bool(dev.get("keep_screen", False)),
                }
            )
            self.data["devices"][device_id] = dev
            self.save()
            return dev

    def rename_device(self, device_id: str, name: str) -> None:
        with self._lock:
            if device_id in self.data["devices"]:
                self.data["devices"][device_id]["name"] = name
                self.save()

    def set_theme(self, device_id: str, theme: str) -> None:
        with self._lock:
            if device_id in self.data["devices"]:
                self.data["devices"][device_id]["theme"] = theme
                self.save()

    def set_keep_screen(self, device_id: str, enabled: bool) -> None:
        with self._lock:
            if device_id in self.data["devices"]:
                self.data["devices"][device_id]["keep_screen"] = bool(enabled)
                self.save()

    def remove_device(self, device_id: str) -> None:
        with self._lock:
            self.data["devices"].pop(device_id, None)
            self.data["assignments"].pop(device_id, None)
            self.save()

    def touch_device(self, device_id: str, ts: str) -> None:
        with self._lock:
            if device_id in self.data["devices"]:
                self.data["devices"][device_id]["last_seen"] = ts
                self.save()

    # -- assignments -------------------------------------------------------
    def assignments(self, device_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self.data["assignments"].get(device_id, {}))

    def set_assignments(self, device_id: str, items: list[dict[str, Any]]) -> None:
        with self._lock:
            self.data["assignments"][device_id] = {
                str(item["module"]): {
                    "enabled": bool(item.get("enabled", True)),
                    "position": int(item.get("position", idx)),
                }
                for idx, item in enumerate(items)
            }
            self.save()
