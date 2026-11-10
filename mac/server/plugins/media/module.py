"""Media module for macOS: master volume, per-device mute, now playing.

Core Audio calls are serialised on one worker thread (the same pattern the
Windows build used for COM): two threads reading and writing the same device
otherwise report a volume that has already moved. Now-playing lives on its own
thread because AppleScript can hang for seconds when an app is busy.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from core import paths
from core.base import Module as BaseModule
from core.mac import audio, media

log = logging.getLogger("deskgadget.media")

STEP = 0.02


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.volume = 0.5
        self.muted = False
        self.device_name = "Default output"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")
        self.mics: list[dict] = []
        self.outputs: list[dict] = []
        self._mic_tick = 0
        self.now: dict | None = None
        self._now_running = False
        self._now_started = 0.0
        self._now_lock = threading.Lock()

    # -- plumbing ----------------------------------------------------------
    async def _call(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, lambda: fn(*args))

    async def on_stop(self) -> None:
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass

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
            self.muted = audio.toggle_mute()
        elif action in ("toggle_endpoint", "mic_toggle"):
            uid = str(payload.get("id", ""))
            if not uid:
                return
            state = audio.toggle_endpoint(uid)
            if state is None:
                log.debug("could not toggle endpoint %s", uid)
                return
            for group in (self.mics, self.outputs):
                for device in group:
                    if device["id"] == uid:
                        device["muted"] = bool(state)
        elif action == "play_pause":
            if media.command("play_pause") and self.now:
                self.now["playing"] = not bool(self.now.get("playing"))
        elif action == "next":
            media.command("next")
        elif action == "prev":
            media.command("prev")
        elif action == "seek":
            media.seek(float(payload.get("value", 0)))

    def _set(self, level: float) -> None:
        level = max(0.0, min(1.0, level))
        audio.set_volume(level)
        self.volume = level
        if level > 0:
            self.muted = False

    # -- state -------------------------------------------------------------
    async def update(self) -> None:
        try:
            self.volume, self.muted = await self._call(audio.get_volume)
            self.device_name = await self._call(audio.default_output_name)
        except Exception:
            log.debug("volume read failed", exc_info=True)

        self._refresh_now()

        # devices change rarely; rescan every ~15s
        self._mic_tick += 1
        if self._mic_tick == 1 or self._mic_tick % 5 == 0:
            try:
                self.outputs, self.mics = await self._call(audio.endpoints)
            except Exception:
                self.outputs, self.mics = [], []

    def _refresh_now(self) -> None:
        """Poll the media session on a throwaway thread; never block audio."""
        with self._now_lock:
            if self._now_running:
                if time.time() - self._now_started < 20:
                    return
                log.debug("media poll is slow; retrying on a new thread")
            self._now_running = True
            self._now_started = time.time()

        def work() -> None:
            value = None
            try:
                value = media.snapshot(paths.data_dir() / "artwork")
            except Exception:
                value = None
            finally:
                with self._now_lock:
                    self.now = value
                    self._now_running = False

        threading.Thread(target=work, name="now-playing", daemon=True).start()

    def page(self) -> dict:
        pct = round(self.volume * 100)
        playing = bool((self.now or {}).get("playing"))
        now = self.now or {}
        has_now = bool(now.get("title"))
        main_col = 1 if has_now else 0
        side_col = 2 if has_now else 1
        blocks: list[dict] = []

        if not media.transport_available():
            blocks.append(
                {
                    "type": "note",
                    "label": "LIMITED MEDIA",
                    "text": "Volume and mute work. Grant Automation for transport, or install nowplaying-cli.",
                    "meta": "The bundled app includes a permission-free helper",
                    "col": 0,
                }
            )

        if has_now:
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
                    "col": 0,
                }
            )
        else:
            blocks.append(
                {
                    "type": "note",
                    "label": "NOTHING PLAYING",
                    "text": "Start something on the Mac — Spotify, Music or a browser.",
                    "meta": "Volume and outputs work regardless",
                    "col": 0,
                }
            )

        blocks += [
            {
                "type": "hero",
                "label": "VOLUME",
                "value": "MUTED" if self.muted else str(pct),
                "unit": "" if self.muted else "%",
                "sub": self.device_name,
                "progress": pct / 100.0,
                "accent": "#FF7AB6",
                "col": main_col,
                "slider": {
                    "action": "set_volume",
                    "value": pct,
                    "min": 0,
                    "max": 100,
                },
            },
            {
                "type": "controls",
                "style": "pill",
                "col": main_col,
                "items": [
                    {
                        "id": "toggle_mute",
                        "icon": "mute" if self.muted else "volume_up",
                        "label": "Unmute" if self.muted else "Mute",
                    },
                    {"id": "prev", "icon": "prev", "label": "Previous"},
                    {
                        "id": "play_pause",
                        "icon": "pause" if playing else "play",
                        "label": "Pause" if playing else "Play",
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
                    "col": side_col,
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
                    "col": 0,
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
