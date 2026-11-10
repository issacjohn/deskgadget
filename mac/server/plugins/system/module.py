"""System monitor for macOS: CPU, memory, disk, network, IPs and quick actions.

Everything here is portable psutil plus the handful of macOS commands that have
existed for a decade. The desktop quick actions live in ``core.mac.power`` so
the permission handling is in one place.
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
import time
from collections import deque

import psutil
import requests

from core.base import Module as BaseModule
from core.mac import NO_WINDOW, power, screen_recording_allowed
from core.netutil import lan_ip


def _gb(value: float) -> float:
    return round(value / (1024 ** 3), 1)


def _root_usage():
    """APFS splits `/` (read-only system) from the Data volume.

    `psutil.disk_usage("/")` reports only the ~13 GB system snapshot, which
    looks like a nearly empty disk. The Data volume reflects the container the
    user actually fills, so prefer it for the root row and fall back on older
    macOS versions where it does not exist.
    """
    data = "/System/Volumes/Data"
    if os.path.isdir(data):
        try:
            return psutil.disk_usage(data)
        except Exception:
            pass
    return psutil.disk_usage("/")


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(
            ["sysctl", "-n", name],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=NO_WINDOW,
        ).stdout.strip()
    except Exception:
        return ""


def _chip_name() -> str:
    """Marketing chip name on Apple Silicon, CPU string on Intel."""
    for key in ("machdep.cpu.brand_string", "hw.model"):
        value = _sysctl(key)
        if value:
            return value[:28]
    return (platform.processor() or "Mac").strip()[:28] or "Mac"


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
        self._boot = psutil.boot_time()
        self.public_ip = "…"
        self.latency: float | None = None
        self._ip_at = 0.0
        self._ping_at = 0.0
        self.batt_percent: float | None = None
        self.batt_plugged = True
        self.batt_left = ""
        self.processes: list[dict] = []
        self._tick = 0
        self._chip = _chip_name()

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

        now = time.time()
        # public address rarely changes; latency is cheap and useful live
        if now - self._ip_at > 600:
            try:
                response = await asyncio.to_thread(
                    requests.get, "https://api.ipify.org", timeout=6
                )
                self.public_ip = response.text.strip() or "…"
                self._ip_at = now
            except Exception:
                pass

        if now - self._ping_at > 30:
            try:
                out = await asyncio.to_thread(
                    subprocess.run,
                    ["ping", "-c", "1", "-W", "1500", "1.1.1.1"],
                    capture_output=True,
                    text=True,
                    timeout=6,
                    creationflags=NO_WINDOW,
                )
                match = re.search(r"time[=<]([0-9.]+)\s*ms", out.stdout or "")
                self.latency = float(match.group(1)) if match else None
                self._ping_at = now
            except Exception:
                self.latency = None

        try:
            battery = psutil.sensors_battery()
        except Exception:
            battery = None
        if battery is None:
            self.batt_percent = None
        else:
            self.batt_percent = float(battery.percent)
            self.batt_plugged = bool(battery.power_plugged)
            self.batt_left = (
                "on AC" if battery.power_plugged else self._minutes(battery.secsleft)
            )

        # process scan is expensive: run it off-loop, a few times a minute
        self._tick += 1
        task = getattr(self, "_scan_task", None)
        if (task is None or task.done()) and (self._tick % 5 == 1 or not self.processes):
            self._scan_task = asyncio.create_task(self._scan_processes())

        mem = psutil.virtual_memory()
        # psutil's macOS `percent` includes compressed/cached pages while
        # `used` does not, which made "8 GB used" sit next to "73%". Use
        # total - available for both so the number and the bar agree.
        used_bytes = max(0, mem.total - mem.available)
        self.mem_percent = round(used_bytes / mem.total * 100, 1) if mem.total else 0.0
        self.mem_used = _gb(used_bytes)
        self.mem_total = _gb(mem.total)

        disk = _root_usage()
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

    def _minutes(self, seconds) -> str:
        if seconds is None or float(seconds) < 0:
            return "calculating"
        minutes = int(float(seconds) // 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m left" if hours else f"{minutes}m left"

    def _rate(self, bps: float) -> str:
        if bps > 1024 ** 2:
            return f"{bps / 1024 ** 2:.1f} MB/s"
        return f"{bps / 1024:.0f} KB/s"

    def _cpu_sub(self) -> str:
        cores = psutil.cpu_count(logical=True) or 1
        parts = [f"{cores} threads", self._chip]
        return " · ".join(part for part in parts if part)

    async def on_action(self, action: str, payload: dict) -> None:
        try:
            if action == "lock":
                power.lock()
                await self.hub.notify("Mac locked")
            elif action == "monitor_off":
                power.display_off()
            elif action == "show_desktop":
                power.show_desktop()
            elif action == "screenshot":
                ok, detail = await asyncio.to_thread(power.screenshot)
                await self.hub.notify(
                    f"Screenshot saved: {detail}" if ok else f"Screenshot failed: {detail}"
                )
        except Exception:
            pass
        self.push()

    def page(self) -> dict:
        uptime = time.time() - self._boot
        hours, rem = divmod(int(uptime), 3600)
        days, hours = divmod(hours, 24)
        uptime_text = f"{days}d {hours}h" if days else f"{hours}h {rem // 60}m"

        gauges = [
            {"label": "CPU", "value": round(self.cpu), "suffix": "%"},
            {"label": "RAM", "value": round(self.mem_percent), "suffix": "%"},
            {"label": "DISK", "value": round(self.disk_percent), "suffix": "%"},
        ]

        blocks: list[dict] = []
        if screen_recording_allowed() is False:
            blocks.append(
                {
                    "type": "note",
                    "label": "PERMISSION",
                    "text": "Screenshots need Screen Recording.",
                    "meta": "Optional",
                    "col": 0,
                }
            )
        blocks += [
            {
                "type": "controls",
                "style": "stack",
                "col": 0,
                "items": [
                    {"id": "lock", "icon": "lock", "label": "Lock Mac"},
                    {"id": "monitor_off", "icon": "screen_off", "label": "Screen off"},
                    {"id": "show_desktop", "icon": "desktop", "label": "Desktop"},
                    {"id": "screenshot", "icon": "camera", "label": "Screenshot"},
                ],
            },
            {
                "type": "gauges",
                "items": gauges,
                "col": 1,
            },
            {
                "type": "meters",
                "col": 1,
                "items": [
                    {
                        "label": "Memory",
                        "value": self.mem_percent,
                        "left": f"{self.mem_used} GB used",
                        "right": f"{self.mem_total} GB",
                    },
                    {
                        "label": "Disk",
                        "value": self.disk_percent,
                        "left": f"{self.disk_free} GB free",
                        "right": f"{self.disk_total} GB",
                    },
                ],
            },
            {
                "type": "kv",
                "col": 2,
                "items": [
                    {"label": "Down", "value": self._rate(self.net_down)},
                    {"label": "Up", "value": self._rate(self.net_up)},
                    {
                        "label": "Ping",
                        "value": (
                            f"{self.latency:.0f} ms" if self.latency is not None else "—"
                        ),
                    },
                ],
            },
            {
                "type": "kv",
                "col": 2,
                "items": [
                    {"label": "Public IP", "value": self.public_ip},
                    {"label": "LAN IP", "value": lan_ip()},
                ],
            },
            (
                {
                    "type": "kv",
                    "col": 2,
                    "items": [
                        {"label": "Battery", "value": f"{self.batt_percent:.0f}%"},
                        {
                            "label": "Power",
                            "value": "AC" if self.batt_plugged else "Battery",
                        },
                        {"label": "Uptime", "value": uptime_text},
                    ],
                }
                if self.batt_percent is not None
                else {
                    "type": "kv",
                    "col": 2,
                    "items": [
                        {"label": "Power", "value": "AC"},
                        {"label": "Battery", "value": "None"},
                        {"label": "Uptime", "value": uptime_text},
                    ],
                }
            ),
        ]
        return {"blocks": blocks}
