"""Timer / Pomodoro running on the PC, driven from the phone."""
from __future__ import annotations

import time

from core.base import Module as BaseModule


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.duration = float(int(self.settings.get("minutes", 25) or 25) * 60)
        self.remaining = self.duration
        self.running = False
        self.deadline = 0.0
        self._finished = False

    async def on_settings(self) -> None:
        self.duration = float(int(self.settings.get("minutes", 25) or 25) * 60)
        if not self.running:
            self.remaining = self.duration
        self.push()

    async def on_action(self, action: str, payload: dict) -> None:
        if action == "start":
            if self.remaining <= 0:
                self.remaining = self.duration
            self.deadline = time.monotonic() + self.remaining
            self.running = True
            self._finished = False
        elif action == "pause":
            if self.running:
                self.remaining = max(0.0, self.deadline - time.monotonic())
            self.running = False
        elif action == "reset":
            self.running = False
            self.remaining = self.duration
            self._finished = False
        elif action == "add5":
            self.remaining += 300
            self.duration = max(self.duration, self.remaining)
            if self.running:
                self.deadline = time.monotonic() + self.remaining
        self.push()

    async def update(self) -> None:
        if not self.running:
            return
        left = self.deadline - time.monotonic()
        self.remaining = max(0.0, left)
        if left <= 0 and not self._finished:
            self.running = False
            self._finished = True
            await self.hub.notify("Timer finished")

    def page(self) -> dict:
        total = max(self.duration, 1.0)
        progress = min(1.0, max(0.0, 1.0 - (self.remaining / total)))
        ends_at = "—"
        if self.running and self.remaining > 0:
            ends_at = time.strftime("%H:%M", time.localtime(time.time() + self.remaining))
        return {
            "blocks": [
                {
                    "type": "hero",
                    "label": "TIMER",
                    "value": _fmt(self.remaining),
                    "unit": "",
                    "sub": "Running" if self.running else ("Done" if self.remaining <= 0 else "Paused"),
                    "progress": progress,
                    "accent": "#B69CFF",
                    "col": 0,
                },
                {
                    "type": "kv",
                    "col": 0,
                    "items": [
                        {"label": "ENDS AT", "value": ends_at},
                        {"label": "LENGTH", "value": f"{int(total // 60)} min"},
                    ],
                },
                {
                    "type": "controls",
                    "style": "pill",
                    "col": 1,
                    "items": [
                        {
                            "id": "pause" if self.running else "start",
                            "icon": "pause" if self.running else "play_pause",
                            "label": "Pause" if self.running else "Start",
                        },
                        {"id": "add5", "icon": "play_pause", "label": "+5 min"},
                        {"id": "reset", "icon": "prev", "label": "Reset"},
                    ],
                },
            ]
        }
