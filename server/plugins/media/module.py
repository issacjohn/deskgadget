"""Media module: controls this PC's volume and transport.

All Core Audio work runs on a single dedicated thread. COM interfaces are
apartment-bound: spreading calls across asyncio's thread pool made writes and
reads land on different endpoints, which is why the reported volume drifted from
what Windows actually had.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core import paths, smtc
from core.base import Module as BaseModule

log = logging.getLogger("liquiddeck.media")

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

STEP = 0.02


def _key(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.volume = 0.5
        self.muted = False
        self.backend = "pycaw"
        self.device_name = "Default output"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")
        self._ep = None
        self.mics: list[dict] = []
        self.outputs: list[dict] = []
        self._mic_tick = 0
        self.now: dict | None = None
        # SMTC lives on its own thread: a wedged WinRT call must never block
        # the Core Audio worker (that froze volume completely)
        self._now_running = False
        self._now_started = 0.0
        self._now_lock = threading.Lock()

    # -- plumbing ----------------------------------------------------------
    def _endpoint(self):
        if self._ep is not None:
            return self._ep
        import comtypes

        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        from pycaw.pycaw import AudioUtilities

        self._ep = AudioUtilities.GetSpeakers().EndpointVolume
        return self._ep

    def _set(self, level: float) -> None:
        """Set the master volume. Runs on the COM worker thread via _call."""
        level = max(0.0, min(1.0, level))
        ep = self._endpoint()
        if ep is None:
            return
        ep.SetMasterVolumeLevelScalar(level, None)
        self.volume = level
        if level > 0:
            self.muted = False

    async def _call(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, lambda: fn(*args))

    # -- actions -----------------------------------------------------------
    async def on_action(self, action: str, payload: dict) -> None:
        try:
            await self._call(self._act, action, payload)
        except Exception:
            log.exception("media action failed: %s", action)
        self.push()

    def _act(self, action: str, payload: dict) -> None:
        if action == "volume_up":
            self._set(self.volume + STEP)
        elif action == "volume_down":
            self._set(self.volume - STEP)
        elif action == "set_volume":
            self._set(float(payload.get("value", 50)) / 100.0)
        elif action == "toggle_mute":
            self._toggle_mute()
        elif action in ("toggle_endpoint", "mic_toggle"):
            self._toggle_endpoint(str(payload.get("id", "")))
        elif action == "play_pause":
            self._media_command("play_pause", VK_MEDIA_PLAY_PAUSE)
        elif action == "next":
            self._media_command("next", VK_MEDIA_NEXT)
        elif action == "prev":
            self._media_command("prev", VK_MEDIA_PREV)
        elif action == "seek":
            seconds = float(payload.get("value", 0))
            threading.Thread(
                target=smtc.seek, args=(seconds,), name="smtc-seek", daemon=True
            ).start()

    def _endpoint_for(self, device_id: str):
        """Both capture and render endpoints are activated the same way."""
        from comtypes import CLSCTX_ALL

        from pycaw.api.endpointvolume import IAudioEndpointVolume
        from pycaw.utils import AudioUtilities

        enumerator = AudioUtilities.GetDeviceEnumerator()
        device = enumerator.GetDevice(device_id)
        iface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return iface.QueryInterface(IAudioEndpointVolume)

    def _toggle_endpoint(self, device_id: str) -> None:
        if not device_id:
            return
        try:
            ep = self._endpoint_for(device_id)
            ep.SetMute(1 if not ep.GetMute() else 0, None)
            muted = bool(self._endpoint_for(device_id).GetMute())
            for group in (self.mics, self.outputs):
                for device in group:
                    if device["id"] == device_id:
                        device["muted"] = muted
        except Exception:
            log.exception("mute toggle failed")

    def _scan_endpoints_sync(self, flow: str) -> list[dict]:
        """Enumerate endpoints of one direction and read their mute state."""
        command = (
            "Get-PnpDevice -Class AudioEndpoint -Status OK -ErrorAction SilentlyContinue"
            f" | Where-Object {{ $_.InstanceId -like '*{flow}*' }}"
            " | ForEach-Object { $_.FriendlyName + '|' + $_.InstanceId }"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.warning("endpoint enumeration failed", exc_info=True)
            return []

        found: list[dict] = []
        lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
        if not lines:
            log.warning(
                "endpoint scan %s empty (rc=%s, err=%s)",
                flow,
                result.returncode,
                (result.stderr or "")[:150],
            )
            return []
        for line in lines:
            if "|" not in line:
                continue
            name, instance = line.split("|", 1)
            dev_id = instance.split("MMDEVAPI\\", 1)[-1].strip()
            if not dev_id.startswith("{"):
                continue
            muted = False
            try:
                muted = bool(self._endpoint_for(dev_id).GetMute())
            except Exception:
                pass
            found.append({"id": dev_id, "name": name.strip(), "muted": muted})
        return found

    # -- state -------------------------------------------------------------
    async def update(self) -> None:
        try:
            await self._call(self._read)
            self.backend = "pycaw"
        except Exception:
            self.backend = "media-keys"

        # non-blocking: SMTC runs on its own thread
        self._refresh_now()

        # devices change rarely; rescan every ~15s
        self._mic_tick += 1
        if self._mic_tick == 1 or self._mic_tick % 5 == 0:
            try:
                self.outputs = await self._call(self._scan_endpoints_sync, "0.0.0.00000000")
                self.mics = await self._call(self._scan_endpoints_sync, "0.0.1.00000000")
            except Exception:
                self.outputs = []
                self.mics = []

    def _read(self) -> None:
        ep = self._endpoint()
        self.volume = float(ep.GetMasterVolumeLevelScalar())
        self.muted = bool(ep.GetMute())

    def _refresh_now(self) -> None:
        """Poll SMTC on a throwaway thread; never block the audio worker."""
        with self._now_lock:
            if self._now_running:
                # Windows' media broker can wedge; let a new thread take over
                # once the old one has been stuck for long enough
                if time.time() - self._now_started < 20:
                    return
                log.warning("SMTC poll has been stuck; retrying on a new thread")
            self._now_running = True
            self._now_started = time.time()

        def work() -> None:
            value = None
            try:
                value = smtc.snapshot(paths.data_dir() / "artwork")
            except Exception:
                value = None
            finally:
                with self._now_lock:
                    self.now = value
                    self._now_running = False

        threading.Thread(target=work, name="smtc-poll", daemon=True).start()

    def _media_command(self, name: str, vk: int) -> None:
        """Use the session API, but still work if WinRT wedges."""
        done = threading.Event()

        def work() -> None:
            try:
                smtc.command(name)
            except Exception:
                pass
            finally:
                done.set()

        threading.Thread(target=work, name=f"smtc-{name}", daemon=True).start()
        if not done.wait(1.2):
            _key(vk)

    def page(self) -> dict:
        pct = round(self.volume * 100)
        blocks: list[dict] = []
        now = self.now or {}
        if now.get("title"):
            blocks.append(
                {
                    "type": "nowplaying",
                    "title": str(now.get("title", "")),
                    "artist": str(now.get("artist") or now.get("album") or ""),
                    "source": str(now.get("source") or ""),
                    "artwork": str(now.get("artwork") or ""),
                    "position": round(float(now.get("position") or 0), 1),
                    "duration": round(float(now.get("duration") or 0), 1),
                    "playing": bool(now.get("playing")),
                    "action": "seek",
                }
            )
        blocks += [
            {
                "type": "hero",
                "label": "PC VOLUME",
                "value": "MUTED" if self.muted else str(pct),
                "unit": "" if self.muted else "%",
                "sub": self.device_name,
                "progress": pct / 100.0,
                "accent": "#FF7AB6",
                "slider": {
                    "action": "set_volume",
                    "value": pct,
                    "min": 0,
                    "max": 100,
                },
            },
            {
                "type": "controls",
                "style": "transport",
                "items": [
                    {
                        "id": "toggle_mute",
                        "icon": "mute" if not self.muted else "volume_up",
                        "label": "Mute",
                    },
                    {"id": "prev", "icon": "prev", "label": "Previous"},
                    {
                        "id": "play_pause",
                        "icon": "play_pause",
                        "label": "Play / Pause",
                        "primary": True,
                    },
                    {"id": "next", "icon": "next", "label": "Next"},
                ],
            },
        ]
        if self.outputs:
            blocks.append(
                {
                    "type": "toggles",
                    "title": "OUTPUTS",
                    "action": "toggle_endpoint",
                    "items": [
                        {
                            "id": dev["id"],
                            "label": dev["name"],
                            "icon": "volume_up",
                            "on": bool(dev["muted"]),
                        }
                        for dev in self.outputs
                    ],
                }
            )
        if self.mics:
            blocks.append(
                {
                    "type": "toggles",
                    "title": "MICROPHONES",
                    "action": "toggle_endpoint",
                    "items": [
                        {
                            "id": mic["id"],
                            "label": mic["name"],
                            "icon": "mic",
                            "on": bool(mic["muted"]),
                        }
                        for mic in self.mics
                    ],
                }
            )
        return {"blocks": blocks}
