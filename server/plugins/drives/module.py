"""Drive space: one ring per volume plus free/total meters."""
from __future__ import annotations

import psutil

from core.base import Module as BaseModule


def _gb(value: float) -> float:
    return round(value / (1024 ** 3), 1)


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.drives: list[dict] = []

    async def update(self) -> None:
        rows = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            rows.append(
                {
                    "mount": part.device.rstrip("\\") or part.mountpoint,
                    "percent": usage.percent,
                    "free": _gb(usage.free),
                    "total": _gb(usage.total),
                }
            )
        self.drives = rows

    def page(self) -> dict:
        if not self.drives:
            return {
                "blocks": [
                    {
                        "type": "hero",
                        "label": "DRIVES",
                        "value": "--",
                        "unit": "",
                        "sub": "No volumes found",
                    }
                ]
            }

        # Rings read well for a handful of volumes; past that the bars are
        # clearer, so skip the ring row instead of shrinking it to specks.
        blocks: list[dict] = []
        if len(self.drives) <= 4:
            blocks.append(
                {
                    "type": "gauges",
                    "items": [
                        {"label": d["mount"], "value": round(d["percent"]), "suffix": "%"}
                        for d in self.drives
                    ],
                }
            )
        blocks.append(
            {
                "type": "meters",
                "items": [
                    {
                        "label": d["mount"],
                        "value": d["percent"],
                        "left": f"{d['free']} GB free",
                        "right": f"{d['total']} GB",
                    }
                    for d in self.drives
                ],
            }
        )
        total_free = round(sum(d["free"] for d in self.drives), 1)
        total_size = round(sum(d["total"] for d in self.drives), 1)
        blocks.append(
            {
                "type": "kv",
                "items": [
                    {"label": "Volumes", "value": str(len(self.drives))},
                    {"label": "Free", "value": f"{total_free} GB"},
                    {"label": "Total", "value": f"{total_size} GB"},
                ],
            }
        )
        return {"blocks": blocks}
