"""Network: public IP, LAN address, latency and throughput."""
from __future__ import annotations

import re
import subprocess
import time

import psutil
import requests

from core.base import Module as BaseModule
from core.netutil import lan_ip


def _rate(bps: float) -> str:
    if bps > 1024 ** 2:
        return f"{bps / 1024 ** 2:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.public_ip = "—"
        self.latency: float | None = None
        self.down = 0.0
        self.up = 0.0
        self._ip_at = 0.0
        self._ping_at = 0.0
        self._sent = None
        self._recv = None
        self._ts = 0.0

    async def update(self) -> None:
        now = time.time()

        if now - self._ip_at > 600:
            try:
                r = requests.get("https://api.ipify.org", timeout=6)
                self.public_ip = r.text.strip() or "—"
                self._ip_at = now
            except Exception:
                pass

        if now - self._ping_at > 30:
            try:
                out = subprocess.run(
                    ["ping", "-n", "1", "-w", "1500", "1.1.1.1"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                ).stdout
                match = re.search(r"(?:time|Time)[=<]([0-9]+)\s*ms", out)
                self.latency = float(match.group(1)) if match else None
                self._ping_at = now
            except Exception:
                self.latency = None

        counters = psutil.net_io_counters()
        if self._sent is not None:
            dt = max(now - self._ts, 0.001)
            self.up = (counters.bytes_sent - self._sent) / dt
            self.down = (counters.bytes_recv - self._recv) / dt
        self._sent, self._recv, self._ts = counters.bytes_sent, counters.bytes_recv, now

    def page(self) -> dict:
        ping = self.latency
        return {
            "blocks": [
                {
                    "type": "hero",
                    "label": "LATENCY",
                    "value": f"{ping:.0f}" if ping is not None else "--",
                    "unit": "ms" if ping is not None else "",
                    "sub": "1.1.1.1",
                    "accent": "#7CE7FF",
                },
                {
                    "type": "kv",
                    "items": [
                        {"label": "Public IP", "value": self.public_ip},
                        {"label": "LAN IP", "value": lan_ip()},
                        {"label": "Host", "value": __import__("socket").gethostname()},
                    ],
                },
                {
                    "type": "kv",
                    "items": [
                        {"label": "Download", "value": _rate(self.down)},
                        {"label": "Upload", "value": _rate(self.up)},
                    ],
                },
            ]
        }
