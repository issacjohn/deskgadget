"""Minimal LiquidDeck module.

A module is two files:
  manifest.json  - id, name, accent colour, update interval, settings schema
  module.py      - a `Module` subclass with update() and page()

`page()` returns a list of blocks. The phone already knows how to draw every
block type, so you never write Android UI.
"""
from __future__ import annotations

import time

from core.base import Module

# Available block types:
#   hero      big number:  label, value, unit, sub, progress, icon, accent
#   gauges    row of rings: items[{label, value, suffix}]
#   sparkline line chart:   label, points[], min, max
#   meters    progress rows: items[{label, value, left, right}]
#   kv        small facts:  items[{label, value}]
#   list      rows:         title, items[{title, sub, value, icon}]
#   controls  buttons:      style ("transport"|"pill"), items[{id, icon, label, primary}]
#   slider    value input:  label, value, min, max, action
#   shortcuts app grid:     title, columns, items[{id, label, icon, path}]
#
# Icons a button can use: prev, next, play_pause, volume_up, volume_down, mute


class Module(Module):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.clicks = 0

    async def on_action(self, action: str, payload: dict) -> None:
        if action == "tap":
            self.clicks += 1
            self.push()  # send the new page to the phone immediately

    def page(self) -> dict:
        greeting = self.settings.get("greeting") or "Hello"
        return {
            "blocks": [
                {
                    "type": "hero",
                    "label": "EXAMPLE",
                    "value": greeting,
                    "unit": "",
                    "sub": time.strftime("%H:%M:%S"),
                },
                {
                    "type": "controls",
                    "style": "pill",
                    "items": [{"id": "tap", "icon": "play_pause", "label": f"Tapped {self.clicks}x"}],
                },
            ]
        }
