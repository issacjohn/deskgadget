"""Battery / UPS state for a laptop or a USB-attached UPS."""
from __future__ import annotations

import logging

import psutil

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.battery")


def _minutes(seconds) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if value < 0 or value > 60 * 60 * 72:
        return "calculating"
    mins = int(value // 60)
    if mins < 60:
        return f"{mins} min"
    return f"{mins // 60}h {mins % 60:02d}m"


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.percent = 0.0
        self.plugged = True
        self.left = ""
        self.present = False

    async def update(self) -> None:
        try:
            battery = psutil.sensors_battery()
        except Exception:
            battery = None
        if battery is None:
            self.present = False
            return
        self.present = True
        self.percent = float(battery.percent)
        self.plugged = bool(battery.power_plugged)
        self.left = _minutes(battery.secsleft) if not battery.power_plugged else "on AC"

    def page(self) -> dict:
        if not self.present:
            return {
                "blocks": [
                    {
                        "type": "hero",
                        "label": "BATTERY",
                        "value": "--",
                        "unit": "",
                        "sub": "No battery on this machine",
                        "accent": self.accent,
                    }
                ]
            }
        return {
            "blocks": [
                {
                    "type": "gauges",
                    "items": [
                        {
                            "label": "BATTERY",
                            "value": round(self.percent),
                            "suffix": "%",
                        }
                    ],
                },
                {
                    "type": "kv",
                    "items": [
                        {"label": "POWER", "value": "AC" if self.plugged else "Battery"},
                        {"label": "TIME LEFT", "value": self.left},
                    ],
                },
                {
                    "type": "meters",
                    "items": [
                        {
                            "label": "CHARGE",
                            "value": round(self.percent),
                            "left": "empty",
                            "right": "full",
                        }
                    ],
                },
            ]
        }
