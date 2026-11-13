"""Media for the Car Thing: now playing and transport, nothing else.

The full Media module owns the Core Audio endpoint, the SMTC poller and the
output list. This page delegates to it, so the phone keeps its richer module
while the Car Thing gets a two-block page with no volume slider and no output
toggles (its volume is the rotary wheel).
"""
from __future__ import annotations

from core.base import Module as BaseModule


class Module(BaseModule):
    def _media(self):
        if not self.hub:
            return None
        return self.hub.modules.get("media")

    def page(self) -> dict:
        media = self._media()
        now = (media.now if media else None) or {}
        playing = bool(now.get("playing"))

        blocks: list[dict] = []
        if now.get("title"):
            blocks.append(
                {
                    "type": "nowplaying",
                    "title": str(now.get("title", "")),
                    "artist": str(now.get("artist") or now.get("album") or ""),
                    "source": str(now.get("source") or ""),
                    "position": round(float(now.get("position") or 0), 1),
                    "duration": round(float(now.get("duration") or 0), 1),
                    "playing": playing,
                    "action": "seek",
                }
            )
        blocks.append(
            {
                "type": "controls",
                "style": "transport",
                "items": [
                    {"id": "prev", "icon": "prev", "label": "Previous"},
                    {
                        "id": "play_pause",
                        "icon": "pause" if playing else "play",
                        "label": "Pause" if playing else "Play",
                        "primary": True,
                    },
                    {"id": "next", "icon": "next", "label": "Next"},
                ],
            }
        )
        return {"blocks": blocks}

    async def on_action(self, action: str, payload: dict) -> None:
        media = self._media()
        if media is None:
            return
        await media.on_action(action, payload)
