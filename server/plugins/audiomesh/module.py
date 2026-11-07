"""AudioMesh module for DeskGadget / DeskGadget.

Phase 1 (this file) works without touching AudioMesh:

* detects whether AudioMesh.exe is running (psutil)
* reads ``%APPDATA%\\AudioMesh\\settings.json`` for the saved configuration
* resolves endpoint names from the Windows MMDevices registry, so the phone
  shows real speaker names even before a control API exists
* can launch the app, or bring it forward once a control API exists

Phase 2 (AudioMesh side, not built yet) adds a loopback HTTP API on
127.0.0.1 that exposes live state and commands. When that is present the
module switches to it automatically -- same page, real controls:

    GET  /api/state
    POST /api/action  {"action": "toggle" | "start" | "stop"
                                | "perfect_sync" | "set_source"
                                | "set_volume" | "set_mute" | "show", ...}

The API is authenticated with an ``X-AudioMesh-Token`` header.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.audiomesh")

DEFAULT_APP = r"C:\Program Files\AudioMesh\AudioMesh.exe"
DEFAULT_PORT = 47823
APP_CANDIDATES = (
    DEFAULT_APP,
    r"C:\Program Files (x86)\AudioMesh\AudioMesh.exe",
)

RENDER_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
NAME_PROP = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
ENUM_PROP = "{a45c254e-df1c-4efd-8020-67d146a850e0},24"

BLUETOOTH_HINTS = (
    "bluetooth", "airpods", "buds", "beats", "hands-free", "headset",
    "wh-1000", "wf-1000", "bose", "jbl", "soundcore", "freebuds",
    "earbuds", "tws", "momentum",
)


def _settings_file() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "AudioMesh" / "settings.json"


def _control_file() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "AudioMesh" / "control.json"


def _display_name(name: str, limit: int = 30) -> str:
    if len(name) <= limit:
        return name
    trimmed = name[: limit - 1]
    cut = trimmed.rfind(" ")
    if cut >= limit // 2:
        trimmed = trimmed[:cut]
    return trimmed.rstrip() + "..."


def _classify(name: str, enumerator: str = "") -> str:
    lower = name.lower()
    enum = enumerator.upper()

    if "BTH" in enum or any(hint in lower for hint in BLUETOOTH_HINTS):
        return "Bluetooth"
    if "USB" in enum or "usb" in lower:
        return "USB"
    if any(hint in lower for hint in ("digital", "spdif", "hdmi", "nvidia", "display")):
        return "Digital"
    if "HDAUDIO" in enum:
        # A HDAUDIO endpoint that is not the codec's speakers/headphones is
        # almost always a monitor over HDMI/DisplayPort.
        if any(hint in lower for hint in ("speaker", "headphone", "realtek", "microphone")):
            return "Analog"
        return "HDMI"
    return "Analog"


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.running = False
        self.api_ok = False
        self.source = "SystemAudio"
        self.perfect_sync = False
        self.latency_mode = "Balanced"
        self.endpoints: list[dict[str, Any]] = []
        self.total = 0
        self.routed_count = 0
        self.notice = ""
        self._notice_until = 0.0
        self._meta: dict[str, tuple[str, str]] = {}
        self._file_port = 0
        self._file_token = ""

    # -- settings ----------------------------------------------------------
    @property
    def port(self) -> int:
        configured = self.settings.get("api_port")
        if configured:
            try:
                return int(configured)
            except (TypeError, ValueError):
                pass
        return self._file_port or DEFAULT_PORT

    @property
    def token(self) -> str:
        configured = str(self.settings.get("api_token") or "").strip()
        return configured or self._file_token

    def _app_path(self) -> str | None:
        configured = str(self.settings.get("app_path") or "").strip().strip('"')
        for candidate in (configured, *APP_CANDIDATES):
            if not candidate:
                continue
            try:
                if Path(candidate).is_file():
                    return candidate
            except OSError:
                continue
        return None

    # -- discovery ---------------------------------------------------------
    @staticmethod
    def _is_running() -> bool:
        try:
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in ("audiomesh.exe", "audiomesh"):
                    return True
        except Exception:
            log.debug("process scan failed", exc_info=True)
        return False

    def _endpoint_meta(self, endpoint_id: str) -> tuple[str, str]:
        """Friendly name and enumerator name ("HDAUDIO", "BTHENUM", "USB")."""
        if endpoint_id in self._meta:
            return self._meta[endpoint_id]

        name = enumerator = ""
        # MMDevice IDs look like "{0.0.0.00000000}.{guid}"; the registry key is
        # just the GUID part.
        registry_id = endpoint_id.rsplit(".", 1)[-1]
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    rf"{RENDER_KEY}\{registry_id}\Properties",
                ) as key:
                    name = str(winreg.QueryValueEx(key, NAME_PROP)[0])
                    try:
                        enumerator = str(winreg.QueryValueEx(key, ENUM_PROP)[0])
                    except OSError:
                        enumerator = ""
            except OSError:
                pass

        self._meta[endpoint_id] = (name, enumerator)
        return name, enumerator

    def _request(self, port: int, method: str, path: str, payload: dict | None = None) -> Any:
        import requests

        url = f"http://127.0.0.1:{port}{path}"
        headers = {"X-AudioMesh-Token": self.token} if self.token else {}
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=0.8)
        else:
            response = requests.post(url, json=payload or {}, headers=headers, timeout=1.2)
        response.raise_for_status()
        return response.json()

    def _api(self, method: str, path: str, payload: dict | None = None) -> Any:
        return self._request(self.port, method, path, payload)

    async def _command(self, payload: dict) -> bool:
        try:
            await asyncio.to_thread(self._api, "POST", "/api/action", payload)
            self.api_ok = True
            return True
        except Exception:
            self.api_ok = False
            return False

    async def _set_all_muted(self, muted: bool) -> int:
        changed = 0
        for endpoint in list(self.endpoints):
            if not endpoint.get("enabled"):
                continue
            if await self._command(
                {"action": "set_mute", "id": endpoint.get("id"), "value": muted}
            ):
                changed += 1
        return changed

    # -- lifecycle ---------------------------------------------------------
    async def update(self) -> None:
        if self.notice and time.time() > self._notice_until:
            self.notice = ""

        # AudioMesh writes port + token here on first launch; prefer it over the
        # dashboard settings so nothing has to be copied by hand.
        self._read_control()
        self.running = await asyncio.to_thread(self._is_running)

        try:
            state = await asyncio.to_thread(self._api, "GET", "/api/state")
        except Exception:
            # The app walks forward if its port is taken, and a restart can leave
            # control.json one number ahead. Probe the small window once.
            state = None
            for candidate in (DEFAULT_PORT, DEFAULT_PORT + 1, DEFAULT_PORT + 2):
                if candidate == self.port:
                    continue
                try:
                    state = await asyncio.to_thread(
                        self._request, candidate, "GET", "/api/state"
                    )
                    self._file_port = candidate
                    break
                except Exception:
                    continue

        self.api_ok = isinstance(state, dict)
        if self.api_ok:
            self._apply_state(state)
        else:
            await asyncio.to_thread(self._apply_settings)

    def _read_control(self) -> None:
        path = _control_file()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            port = int(data.get("port") or data.get("Port") or 0)
            if not self._file_port:
                self._file_port = port
            self._file_token = str(data.get("token") or data.get("Token") or "")
        except (OSError, ValueError, TypeError):
            log.debug("could not read %s", path, exc_info=True)

    def _apply_state(self, state: dict) -> None:
        self.running = bool(state.get("running", True))
        self.source = str(state.get("source") or "SystemAudio")
        self.perfect_sync = bool(state.get("perfectSync"))
        self.latency_mode = str(state.get("bufferMode") or "Balanced")

        endpoints = state.get("endpoints") or []
        self.endpoints = [e for e in endpoints if isinstance(e, dict)]
        self.total = len(self.endpoints)
        self.routed_count = sum(1 for e in self.endpoints if e.get("enabled"))

    def _apply_settings(self) -> None:
        path = _settings_file()
        if path is None or not path.is_file():
            self.endpoints = []
            self.total = 0
            self.routed_count = 0
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.debug("could not read %s", path, exc_info=True)
            return

        self.source = str(data.get("Source") or "SystemAudio")
        self.perfect_sync = bool(data.get("PerfectSync"))
        self.latency_mode = str(data.get("LatencyMode") or "Balanced")

        devices = data.get("Devices") or {}
        order = [i for i in (data.get("DeviceOrder") or []) if i in devices]
        order += [i for i in devices if i not in order]

        endpoints = []
        for endpoint_id in order:
            saved = devices.get(endpoint_id) or {}
            name, enumerator = self._endpoint_meta(endpoint_id)
            name = name or "Endpoint"
            endpoints.append(
                {
                    "id": endpoint_id,
                    "name": name,
                    "kind": _classify(name, enumerator),
                    "enabled": bool(saved.get("Enabled")),
                    "volume": saved.get("Volume") or 0,
                    "muted": bool(saved.get("Muted")),
                    "delayMs": int(saved.get("DelayMs") or 0),
                    "bufferMs": None,
                    "driftPpm": None,
                }
            )

        self.endpoints = endpoints
        self.total = len(endpoints)
        self.routed_count = sum(1 for e in endpoints if e["enabled"])

    # -- actions -----------------------------------------------------------
    async def on_action(self, action: str, payload: dict) -> None:
        if action == "launch":
            await self._launch()
            self.push()
            return

        if action == "refresh":
            await self.update()
            self.push()
            if not self.api_ok:
                await self.hub.notify("Refreshed - control API not reachable")
            return

        if not self.api_ok:
            self._set_notice("Live controls arrive with the control API")
            self.push()
            return

        value = payload.get("value")
        if action == "toggle":
            await self._command({"action": "toggle"})
        elif action == "perfect_sync":
            await self._command({"action": "perfect_sync", "value": not self.perfect_sync})
        elif action == "source":
            target = "system" if self.source == "TestTone" else "tone"
            await self._command({"action": "set_source", "value": target})
        elif action == "set_volume":
            try:
                volume = max(0, min(100, int(value)))
            except (TypeError, ValueError):
                volume = 50
            await self._command({"action": "set_volume", "value": volume})
        elif action == "show":
            await self._command({"action": "show"})
        elif action == "estimate":
            if await self._command({"action": "estimate"}):
                await self.hub.notify("Delays estimated - trim by ear with the test tone")
        elif action == "toggle_device":
            endpoint_id = str(payload.get("id") or "")
            target = next(
                (e for e in self.endpoints if str(e.get("id")) == endpoint_id), None
            )
            if target is not None:
                want = not bool(target.get("enabled"))
                ok = await self._command(
                    {"action": "set_enabled", "id": endpoint_id, "value": want}
                )
                await asyncio.to_thread(self._refresh_now)
                current = next(
                    (e for e in self.endpoints if str(e.get("id")) == endpoint_id), None
                )
                actual = bool(current.get("enabled")) if current else False
                if ok and actual == want:
                    await self.hub.notify(
                        f"{'Enabled' if want else 'Disabled'} {_display_name(str(target.get('name') or 'speaker'))}"
                    )
                elif ok:
                    await self.hub.notify("That output is the capture source")
                self.push()
                return
        elif action == "mute_all":
            any_unmuted = any(e.get("enabled") and not e.get("muted") for e in self.endpoints)
            changed = await self._set_all_muted(any_unmuted)
            if self.api_ok and changed:
                word = "Muted" if any_unmuted else "Unmuted"
                await self.hub.notify(f"{word} {changed} speaker{'s' if changed != 1 else ''}")

        if self.api_ok:
            self._set_notice("")
        else:
            self._set_notice("AudioMesh did not answer")

        await asyncio.to_thread(self._refresh_now)
        self.push()

    def _set_notice(self, text: str) -> None:
        self.notice = text
        self._notice_until = time.time() + (6 if text else 0)

    def _refresh_now(self) -> None:
        try:
            self._apply_state(self._api("GET", "/api/state"))
            self.running = True
        except Exception:
            self.api_ok = False

    async def _launch(self) -> None:
        if self.running:
            if self.api_ok:
                await self._command({"action": "show"})
            else:
                self._set_notice("Already running - open it from the tray")
            return

        path = self._app_path()
        if not path:
            self._set_notice("Set the AudioMesh.exe path in settings")
            return

        try:
            flags = 0
            if os.name == "nt":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([path], close_fds=True, creationflags=flags)
            self._set_notice("Launching AudioMesh...")
            await asyncio.sleep(1.5)
            self.running = await asyncio.to_thread(self._is_running)
        except Exception:
            log.exception("could not launch %s", path)
            self._set_notice("Could not launch AudioMesh")

    # -- page --------------------------------------------------------------
    def _row(self, endpoint: dict) -> dict:
        kind = str(endpoint.get("kind") or "Output")
        name = _display_name(str(endpoint.get("name") or "Endpoint"), 24)
        volume = endpoint.get("volume")

        if not endpoint.get("enabled"):
            sub = f"{kind} - off"
            value = "off"
        else:
            buffer_ms = endpoint.get("bufferMs")
            delay_ms = int(endpoint.get("delayMs") or 0)
            if buffer_ms:
                sub = f"{kind} - {buffer_ms} ms"
            elif delay_ms:
                sub = f"{kind} - {delay_ms} ms"
            else:
                sub = kind
            value = "muted" if endpoint.get("muted") else f"{int(volume or 0)}%"

        return {
            "title": name,
            "sub": sub,
            "value": value,
            "action": "toggle_device",
            "id": endpoint.get("id"),
        }

    def page(self) -> dict:
        enabled = [e for e in self.endpoints if e.get("enabled")]
        volumes = [int(e.get("volume") or 0) for e in enabled]
        average = round(sum(volumes) / len(volumes)) if volumes else 100
        all_muted = bool(enabled) and all(e.get("muted") for e in enabled)

        if self.api_ok:
            if self.running and all_muted:
                hero_value = "MUTED"
            elif self.running:
                hero_value = "LIVE"
            else:
                hero_value = "READY"
        elif self.running:
            hero_value = "RUNNING"
        else:
            hero_value = "OFFLINE"

        routed_text = (
            f"{self.routed_count} of {self.total} routed"
            if self.total
            else "No speakers configured"
        )
        hero_sub = routed_text + (f" | {average}%" if enabled else "")

        blocks: list[dict] = [
            {
                "type": "hero",
                "label": "AUDIOMESH",
                "value": hero_value,
                "unit": "",
                "sub": self.notice or hero_sub,
                "progress": (average / 100.0) if enabled else ((self.routed_count / self.total) if self.total else 0.0),
                "accent": "#4C8DFF",
                "col": 0,
            }
        ]

        if not self.api_ok:
            blocks.append(
                {
                    "type": "controls",
                    "style": "pill",
                    "col": 1,
                    "items": [
                        {
                            "id": "launch",
                            "icon": "desktop",
                            "label": "Open" if self.running else "Launch",
                        },
                        {"id": "refresh", "icon": "refresh", "label": "Refresh"},
                    ],
                }
            )
            if self.endpoints:
                blocks.append(
                    {
                        "type": "list",
                        "title": "SPEAKERS",
                        "col": 2,
                        "items": [self._row(e) for e in self.endpoints],
                    }
                )
            return {"blocks": blocks}

        # Volume lives with the hero so AUDIOMESH shows the level at a glance.
        blocks.append(
            {
                "type": "slider",
                "label": "ALL SPEAKERS",
                "value": average,
                "min": 0,
                "max": 100,
                "action": "set_volume",
                "col": 0,
            }
        )
        blocks.append(
            {
                "type": "kv",
                "col": 0,
                "items": [
                    {
                        "label": "SOURCE",
                        "value": "Tone" if self.source == "TestTone" else "System",
                    },
                    {"label": "BUFFER", "value": self.latency_mode or "Balanced"},
                ],
            }
        )

        blocks.append(
            {
                "type": "controls",
                "style": "pill",
                "col": 1,
                "items": [
                    {
                        "id": "toggle",
                        "icon": "pause" if self.running else "play_pause",
                        "label": "Stop" if self.running else "Start",
                    },
                    {
                        "id": "perfect_sync",
                        "icon": "sync",
                        "label": "Sync on" if self.perfect_sync else "Sync off",
                    },
                    {
                        "id": "source",
                        "icon": "music_note",
                        "label": "Tone" if self.source != "TestTone" else "System",
                    },
                ],
            }
        )

        any_unmuted = any(e.get("muted") is False for e in enabled)
        blocks.append(
            {
                "type": "controls",
                "style": "pill",
                "col": 2,
                "items": [
                    {"id": "estimate", "icon": "straighten", "label": "Estimate"},
                    {
                        "id": "mute_all",
                        "icon": "mute" if any_unmuted else "volume_up",
                        "label": "Mute all" if any_unmuted else "Unmute",
                    },
                ],
            }
        )

        routed_rows = [self._row(e) for e in enabled]
        available_rows = [self._row(e) for e in self.endpoints if not e.get("enabled")]

        if routed_rows:
            blocks.append(
                {
                    "type": "list",
                    "title": "ROUTED",
                    "col": 1,
                    "items": routed_rows,
                }
            )
        if available_rows:
            blocks.append(
                {
                    "type": "list",
                    "title": "AVAILABLE",
                    "col": 2,
                    "items": available_rows,
                }
            )

        return {"blocks": blocks}

