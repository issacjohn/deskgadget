"""System monitor: CPU, memory, disk, network, top processes and quick actions."""
from __future__ import annotations

import asyncio
import ctypes
import platform
import re
import subprocess
import time
from collections import deque

import psutil
import requests

from core.base import Module as BaseModule
from core.netutil import lan_ip

VK_LWIN = 0x5B
VK_SHIFT = 0x10
KEY_D = 0x44
HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
KEYEVENTF_KEYUP = 0x0002


def _combo(*keys: int) -> None:
    user32 = ctypes.windll.user32
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)


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
        self._boot = psutil.boot_time()
        self.public_ip = "…"
        self.latency: float | None = None
        self._ip_at = 0.0
        self._ping_at = 0.0
        self.batt_percent: float | None = None
        self.batt_plugged = True
        self.batt_left = ""

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
                    ["ping", "-n", "1", "-w", "1500", "1.1.1.1"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                match = re.search(r"(?:time|Time)[=<]([0-9]+)\s*ms", out.stdout or "")
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

    async def on_action(self, action: str, payload: dict) -> None:
        try:
            if action == "lock":
                ctypes.windll.user32.LockWorkStation()
                await self.hub.notify("PC locked")
            elif action == "monitor_off":
                ctypes.windll.user32.SendMessageW(
                    HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2
                )
            elif action == "show_desktop":
                _combo(VK_LWIN, KEY_D)
            elif action == "screenshot":
                _combo(VK_LWIN, VK_SHIFT, 0x53)
                await self.hub.notify("Snipping tool open")
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
        if self.batt_percent is not None:
            gauges.append(
                {"label": "BATT", "value": round(self.batt_percent), "suffix": "%"}
            )

        blocks = [
            {
                "type": "gauges",
                "items": gauges,
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
            {
                "type": "kv",
                "items": [
                    {"label": "Public IP", "value": self.public_ip},
                    {"label": "LAN IP", "value": lan_ip()},
                    {
                        "label": "Latency",
                        "value": (
                            f"{self.latency:.0f} ms"
                            if self.latency is not None
                            else "—"
                        ),
                    },
                ],
            },
            (
                {
                    "type": "kv",
                    "items": [
                        {"label": "Battery", "value": f"{self.batt_percent:.0f}%"},
                        {
                            "label": "Power",
                            "value": "AC" if self.batt_plugged else "Battery",
                        },
                        {"label": "Time left", "value": self.batt_left},
                    ],
                }
                if self.batt_percent is not None
                else {
                    "type": "kv",
                    "items": [
                        {"label": "Power", "value": "Plugged in"},
                        {"label": "Battery", "value": "None on this PC"},
                    ],
                }
            ),
            {
                "type": "controls",
                "style": "pill",
                "items": [
                    {"id": "lock", "icon": "mute", "label": "Lock PC"},
                    {"id": "monitor_off", "icon": "mute", "label": "Screen off"},
                    {"id": "show_desktop", "icon": "grid", "label": "Desktop"},
                    {"id": "screenshot", "icon": "camera", "label": "Screenshot"},
                ],
            },
        ]
        return {"blocks": blocks}
