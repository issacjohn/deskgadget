"""Drive space for macOS: one ring per volume plus free/total meters.

psutil already understands APFS. The only macOS-specific part is presentation:
skip the synthetic ``/System/Volumes/*`` mounts (they are the same container as
``/`` and would show up three times) and use volume names instead of device
nodes like ``/dev/disk3s1s1``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psutil

from core.base import Module as BaseModule


def _gb(value: float) -> float:
    return round(value / (1024 ** 3), 1)


def _usage(mountpoint: str):
    """Root uses the APFS Data volume; `/` alone is a tiny read-only snapshot."""
    if mountpoint == "/" and os.path.isdir("/System/Volumes/Data"):
        try:
            return psutil.disk_usage("/System/Volumes/Data")
        except Exception:
            pass
    return psutil.disk_usage(mountpoint)


def _label(mountpoint: str) -> str:
    if sys.platform == "darwin":
        if mountpoint == "/":
            return "Macintosh HD"
        name = Path(mountpoint).name
        return name or mountpoint
    return mountpoint


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.drives: list[dict] = []

    async def update(self) -> None:
        rows = []
        seen: set[str] = set()
        for part in psutil.disk_partitions(all=False):
            mount = part.mountpoint
            # APFS exposes the data/system split as separate mounts; only show
            # user-facing volumes, otherwise "/" appears three times.
            if mount.startswith("/System/Volumes/"):
                continue
            if mount in seen:
                continue
            try:
                usage = _usage(mount)
            except Exception:
                continue
            seen.add(mount)
            rows.append(
                {
                    "mount": _label(mount),
                    "percent": usage.percent,
                    "free": _gb(usage.free),
                    "total": _gb(usage.total),
                }
            )
        rows.sort(key=lambda row: (row["mount"] != "Macintosh HD", row["mount"].lower()))
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
