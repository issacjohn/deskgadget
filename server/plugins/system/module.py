"""System monitor: CPU, memory, disk, network, top processes and quick actions."""
from __future__ import annotations

import asyncio
import ctypes
import os
import platform
import re
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

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
        self.cpu_temp: float | None = None
        self.gpu_temp: float | None = None
        self.gpu_name = ""
        self._lhm = None
        self._temp_at = 0.0
        self._temp_task: asyncio.Task | None = None

    async def on_start(self) -> None:
        psutil.cpu_percent(None)
        self._fill_history()

    def _fill_history(self) -> None:
        if not self.history:
            for _ in range(48):
                self.history.append(self.cpu)

    # -- temperatures ------------------------------------------------------
    def _load_lhm(self) -> None:
        if self._lhm is not None:
            return
        try:
            import clr

            folder = Path(__file__).with_name("lhm")
            if str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
            clr.AddReference(str(folder / "LibreHardwareMonitorLib.dll"))
            from LibreHardwareMonitor.Hardware import Computer

            computer = Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.Open()
            self._lhm = computer
        except Exception:
            self._lhm = None

    def _read_temps_sync(self) -> None:
        self._load_lhm()
        cpu: float | None = None
        gpu: float | None = None
        gpu_name = ""
        computer = self._lhm
        if computer is not None:
            try:
                for hardware in computer.Hardware:
                    hardware.Update()
                    kind = str(hardware.HardwareType)
                    if "Cpu" in kind:
                        values = []
                        for sensor in hardware.Sensors:
                            if str(sensor.SensorType) != "Temperature" or sensor.Value is None:
                                continue
                            name = str(sensor.Name)
                            if "Package" in name or "Tctl" in name:
                                cpu = float(sensor.Value)
                                break
                            values.append(float(sensor.Value))
                        if cpu is None and values:
                            cpu = max(values)
                    elif "Gpu" in kind and gpu is None:
                        for sensor in hardware.Sensors:
                            if (
                                str(sensor.SensorType) == "Temperature"
                                and sensor.Value is not None
                                and "Core" in str(sensor.Name)
                            ):
                                gpu = float(sensor.Value)
                                gpu_name = str(hardware.Name)
                                break
            except Exception:
                pass

        if gpu is None:
            try:
                output = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                line = (output.stdout or "").strip().splitlines()
                if line:
                    parts = [p.strip() for p in line[0].split(",")]
                    if len(parts) >= 2 and parts[1]:
                        gpu_name = parts[0]
                        gpu = float(parts[1])
            except Exception:
                pass

        if cpu is None and time.time() - getattr(self, "_acpi_at", 0.0) > 60:
            self._acpi_at = time.time()
            try:
                output = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "$t=(Get-CimInstance -Namespace root/WMI "
                        "-ClassName MSAcpi_ThermalZoneTemperature "
                        "-ErrorAction SilentlyContinue | Measure-Object "
                        "CurrentTemperature -Maximum).Maximum; "
                        "if($t){[math]::Round($t/10-273.15,1)}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=6,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                text = (output.stdout or "").strip()
                if text:
                    cpu = float(text)
            except Exception:
                pass

        self.cpu_temp = cpu
        self.gpu_temp = gpu
        if gpu_name:
            self.gpu_name = gpu_name

    async def _read_temps(self) -> None:
        try:
            await asyncio.to_thread(self._read_temps_sync)
        except Exception:
            pass

    async def update(self) -> None:
        self.cpu = psutil.cpu_percent(None)
        self.history.append(round(self.cpu, 1))

        now = time.time()
        if now - self._temp_at > 2.0:
            self._temp_at = now
            if self._temp_task is None or self._temp_task.done():
                self._temp_task = asyncio.create_task(self._read_temps())
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

        power_items = [
            {
                "label": "Power",
                "value": "AC" if self.batt_plugged else "Battery",
            }
        ]
        if self.batt_percent is not None:
            power_items.append(
                {"label": "Battery", "value": f"{self.batt_percent:.0f}%"}
            )
        power_items.extend(
            [
                {"label": "Uptime", "value": uptime_text},
                {"label": "LAN IP", "value": lan_ip()},
                {"label": "Public IP", "value": self.public_ip},
            ]
        )

        blocks = [
            {
                "type": "controls",
                "style": "stack",
                "col": 0,
                "items": [
                    {"id": "lock", "icon": "lock", "label": "Lock PC"},
                    {"id": "monitor_off", "icon": "screen_off", "label": "Screen off"},
                    {"id": "show_desktop", "icon": "desktop", "label": "Desktop"},
                    {"id": "screenshot", "icon": "camera", "label": "Screenshot"},
                ],
            },
            {
                "type": "kv",
                "col": 0,
                "items": power_items,
            },
            {
                "type": "gauges",
                "items": gauges,
                "col": 1,
            },
            {
                "type": "sparkline",
                "label": "CPU LOAD",
                "points": [round(v, 1) for v in self.history],
                "min": 0,
                "max": 100,
                "col": 1,
            },
            {
                "type": "thermals",
                "col": 2,
                "cpu": None if self.cpu_temp is None else round(self.cpu_temp),
                "gpu": None if self.gpu_temp is None else round(self.gpu_temp),
                "cpu_name": "package" if self.cpu_temp is not None else "admin required",
                "gpu_name": self.gpu_name
                or ("unavailable" if self.gpu_temp is None else "GPU"),
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
        ]
        return {"blocks": blocks}
