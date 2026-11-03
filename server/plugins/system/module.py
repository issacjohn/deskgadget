"""System monitor module: CPU, memory, disk, network, top processes."""
from __future__ import annotations

import asyncio
import platform
import time
from collections import deque

import psutil

from core.base import Module as BaseModule


def _gb(value: float) -> float:
    return round(value / (1024 ** 3), 1)


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.cpu = 0.0
        self.mem_percent = 0.0
        self.mem_used = 0.0
        self.mem_total = 0.0
        self.disk_percent = 0.0
        self.disk_free = 0.0
        self.disk_total = 0.0
        self.net_up = 0.0
        self.net_down = 0.0
        self.history: deque[float] = deque(maxlen=48)
        self.processes: list[dict] = []
        self._boot = psutil.boot_time()

    async def on_start(self) -> None:
        psutil.cpu_percent(None)
        self._fill_history()

    def _fill_history(self) -> None:
        if not self.history:
            for _ in range(48):
                self.history.append(self.cpu)

    async def update(self) -> None:
        self.cpu = psutil.cpu_percent(None)
        self.history.append(round(self.cpu, 1))

        mem = psutil.virtual_memory()
        self.mem_percent = mem.percent
        self.mem_used = _gb(mem.used)
        self.mem_total = _gb(mem.total)

        disk = psutil.disk_usage("C:\\")
        self.disk_percent = disk.percent
        self.disk_free = _gb(disk.free)
        self.disk_total = _gb(disk.total)

        net = psutil.net_io_counters()
        now = time.time()
        dt = max(now - getattr(self, "_net_ts", now), 0.001)
        up = (net.bytes_sent - getattr(self, "_net_sent", net.bytes_sent)) / dt
        down = (net.bytes_recv - getattr(self, "_net_recv", net.bytes_recv)) / dt
        self._net_sent, self._net_recv, self._net_ts = net.bytes_sent, net.bytes_recv, now
        self.net_up = up
        self.net_down = down

        # the process scan is the expensive part; run it off-loop and only
        # every few seconds so the 1s cadence never waits on it
        self._tick = getattr(self, "_tick", 0) + 1
        if not self.settings.get("show_processes", True):
            return
        task = getattr(self, "_scan_task", None)
        if (task is None or task.done()) and (self._tick % 4 == 1 or not self.processes):
            self._scan_task = asyncio.create_task(self._scan_processes())

    async def _scan_processes(self) -> None:
        try:
            self.processes = await asyncio.to_thread(self._scan_processes_sync)
        except Exception:
            pass

    def _scan_processes_sync(self) -> list[dict]:
        rows = []
        for proc in sorted(
            psutil.process_iter(["pid", "name", "memory_info"]),
            key=lambda p: (p.info.get("memory_info").rss if p.info.get("memory_info") else 0),
            reverse=True,
        )[:4]:
            info = proc.info
            mib = (info.get("memory_info").rss / (1024 ** 2)) if info.get("memory_info") else 0
            rows.append(
                {
                    "title": (info.get("name") or "?")[:26],
                    "sub": f"PID {info.get('pid')}",
                    "value": f"{mib:.0f} MB",
                }
            )
        return rows

    def _rate(self, bps: float) -> str:
        if bps > 1024 ** 2:
            return f"{bps / 1024 ** 2:.1f} MB/s"
        return f"{bps / 1024:.0f} KB/s"

    def _cpu_sub(self) -> str:
        cores = psutil.cpu_count(logical=True) or 1
        try:
            freq = psutil.cpu_freq()
            ghz = f"{freq.current / 1000:.1f} GHz" if freq and freq.current else ""
        except Exception:
            ghz = ""
        name = (platform.processor() or "").split(",")[0].strip()
        parts = [f"{cores} threads"]
        if ghz:
            parts.append(ghz)
        elif name:
            parts.append(name[:22])
        return " · ".join(parts)

    def page(self) -> dict:
        uptime = time.time() - self._boot
        hours, rem = divmod(int(uptime), 3600)
        days, hours = divmod(hours, 24)
        uptime_text = f"{days}d {hours}h" if days else f"{hours}h {rem // 60}m"

        blocks = [
            {
                "type": "gauges",
                "items": [
                    {"label": "CPU", "value": round(self.cpu), "suffix": "%"},
                    {"label": "RAM", "value": round(self.mem_percent), "suffix": "%"},
                    {"label": "DISK", "value": round(self.disk_percent), "suffix": "%"},
                ],
            },
            {
                "type": "hero",
                "label": "CPU LOAD",
                "value": f"{self.cpu:.0f}",
                "unit": "%",
                "sub": self._cpu_sub(),
                "progress": self.cpu / 100,
            },
            {
                "type": "sparkline",
                "label": "CPU HISTORY",
                "points": list(self.history),
                "min": 0,
                "max": 100,
            },
            {
                "type": "meters",
                "items": [
                    {
                        "label": "Memory",
                        "value": self.mem_percent,
                        "left": f"{self.mem_used} GB used",
                        "right": f"{self.mem_total} GB",
                    },
                    {
                        "label": "Disk C:",
                        "value": self.disk_percent,
                        "left": f"{self.disk_free} GB free",
                        "right": f"{self.disk_total} GB",
                    },
                ],
            },
            {
                "type": "kv",
                "items": [
                    {"label": "Download", "value": self._rate(self.net_down)},
                    {"label": "Upload", "value": self._rate(self.net_up)},
                    {"label": "Uptime", "value": uptime_text},
                ],
            },
        ]
        if self.processes:
            blocks.append({"type": "list", "title": "TOP PROCESSES", "items": self.processes})
        return {"blocks": blocks}
