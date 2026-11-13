"""System monitor: CPU, memory, disk, network, top processes and quick actions."""
from __future__ import annotations

import asyncio
import ctypes
import json
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

PAWNIO_URL = (
    "https://github.com/namazso/PawnIO.Setup/releases/latest/download/PawnIO_setup.exe"
)

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
        self.gpu_hot: float | None = None
        self.gpu_memory: float | None = None
        self.gpu_name = ""
        self._lhm = None
        self._temp_at = 0.0
        self._temp_task: asyncio.Task | None = None

    async def on_start(self) -> None:
        self.cpu = psutil.cpu_percent(None)
        self._fill_history()

    def _fill_history(self) -> None:
        if not self.history:
            for _ in range(48):
                self.history.append(self.cpu)

    # -- temperatures ------------------------------------------------------
    # CPU package temperature is only readable through the debug interface that
    # LibreHardwareMonitor drives, and that needs administrator rights. A tiny
    # helper process (this exe with --sensors) does the .NET work and writes
    # sensors.json; the server never loads .NET itself, which keeps it stable.
    def _sensor_files(self) -> list[Path]:
        paths: list[Path] = []
        try:
            from core.paths import data_dir

            paths.append(data_dir() / "sensors.json")
        except Exception:
            pass
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        paths.append(Path(base) / "DeskGadget" / "sensors.json")
        return paths

    def _sensor_fresh(self) -> bool:
        for path in self._sensor_files():
            try:
                if time.time() - path.stat().st_mtime <= 15:
                    return True
            except OSError:
                continue
        return False

    def _sensor_file_temp(self) -> float | None:
        for path in self._sensor_files():
            try:
                if time.time() - path.stat().st_mtime > 15:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("gpu") is not None:
                    self.gpu_temp = float(data["gpu"])
                if data.get("hot") is not None:
                    self.gpu_hot = float(data["hot"])
                if data.get("memory") is not None:
                    self.gpu_memory = float(data["memory"])
                if data.get("name"):
                    self.gpu_name = str(data["name"])
                if data.get("cpu") is not None:
                    return float(data["cpu"])
            except Exception:
                continue
        return None

    def _sensor_ready(self) -> bool:
        if self.cpu_temp is not None:
            return True
        for path in self._sensor_files():
            try:
                if time.time() - path.stat().st_mtime > 15:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("cpu") is not None:
                    return True
            except Exception:
                continue
        return False

    def _ensure_sensor_process(self) -> None:
        """Start the unelevated helper when no elevated one is feeding us."""
        if self._sensor_fresh():
            return
        proc = getattr(self, "_sensor_proc", None)
        if proc is not None and proc.poll() is None:
            return
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--sensors"]
        else:
            launcher = Path(__file__).resolve().parents[3] / "packaging" / "launcher.py"
            command = [sys.executable, str(launcher), "--sensors"]
        try:
            self._sensor_proc = subprocess.Popen(
                command,
                cwd=str(Path.home()),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            self._sensor_proc = None

    def _pawnio_installed(self) -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\PawnIO",
            )
            key.Close()
            return True
        except OSError:
            return False

    def _download_pawnio(self) -> Path | None:
        target = Path(os.environ.get("TEMP", ".")) / "PawnIO_setup.exe"
        try:
            if target.exists() and target.stat().st_size > 1_000_000:
                return target
            response = requests.get(PAWNIO_URL, timeout=60)
            response.raise_for_status()
            target.write_bytes(response.content)
            return target if target.stat().st_size > 1_000_000 else None
        except Exception:
            return None

    def _sensor_setup_script(self, pawnio: str) -> str:
        if getattr(sys, "frozen", False):
            command = f'"{sys.executable}" --sensors'
        else:
            launcher = Path(__file__).resolve().parents[3] / "packaging" / "launcher.py"
            command = f'"{sys.executable}" "{launcher}" --sensors'
        return f"""
$ErrorActionPreference = 'Stop'
$pawnio = '{pawnio}'
$command = '{command}'
if ($pawnio) {{
  $sig = Get-AuthenticodeSignature $pawnio
  if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'namazso') {{ throw 'PawnIO signature check failed' }}
  Start-Process -FilePath $pawnio -Wait
}}
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c start "" /min ' + $command)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -RunLevel Highest -LogonType Interactive
Get-CimInstance Win32_Process -Filter "Name='DeskGadget.exe'" | Where-Object {{ $_.CommandLine -match '--sensors' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
Start-Sleep -Seconds 2
Register-ScheduledTask -TaskName 'DeskGadgetSensors' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName 'DeskGadgetSensors'
"""

    def _install_sensor_task(self) -> bool:
        """Install PawnIO when missing, then (re)start the elevated helper.

        LibreHardwareMonitor reads CPU package temperature through PawnIO, a
        signed kernel driver by namazso (pawnio.eu). It is downloaded from the
        official release rather than bundled, its signature is checked, and the
        official installer is shown so the user approves the driver.
        """
        pawnio = "" if self._pawnio_installed() else (self._download_pawnio() or "")
        script_text = self._sensor_setup_script(pawnio)
        script = Path(os.environ.get("TEMP", ".")) / "deskgadget-sensors.ps1"
        try:
            script.write_text(script_text, encoding="utf-8-sig")
            launch = (
                "Start-Process -FilePath 'powershell.exe' -ArgumentList "
                f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script}' "
                "-Verb RunAs -Wait -WindowStyle Hidden"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", launch],
                capture_output=True,
                text=True,
                timeout=360,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0 and self._pawnio_installed()
        except Exception:
            return False
        finally:
            try:
                script.unlink()
            except OSError:
                pass

    def _read_temps_sync(self) -> None:
        self._ensure_sensor_process()
        cpu = self._sensor_file_temp()

        if self.gpu_temp is None:
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
                        self.gpu_name = parts[0]
                        self.gpu_temp = float(parts[1])
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
            elif action == "cpu_sensor":
                await self.hub.notify("Approve the Windows prompt")
                ok = await asyncio.to_thread(self._install_sensor_task)
                await self.hub.notify(
                    "CPU sensor enabled" if ok else "CPU sensor not enabled"
                )
                self._temp_at = 0.0
        except Exception:
            pass
        self.push()

    def page(self) -> dict:
        uptime = time.time() - self._boot
        hours, rem = divmod(int(uptime), 3600)
        days, hours = divmod(hours, 24)
        uptime_text = f"{days}d {hours}h" if days else f"{hours}h {rem // 60}m"

        cpu_temp = None if self.cpu_temp is None else round(self.cpu_temp)
        gpu_temp = None if self.gpu_temp is None else round(self.gpu_temp)

        actions = [
            {"id": "lock", "icon": "lock", "label": "Lock PC"},
            {"id": "monitor_off", "icon": "screen_off", "label": "Screen off"},
            {"id": "show_desktop", "icon": "desktop", "label": "Desktop"},
            {"id": "screenshot", "icon": "camera", "label": "Capture"},
        ]
        info_items = [
            {"label": "Power", "value": "AC" if self.batt_plugged else "Battery"},
            {"label": "Uptime", "value": uptime_text},
            {"label": "LAN IP", "value": lan_ip()},
            {"label": "Public IP", "value": self.public_ip},
        ]
        if self.batt_percent is not None:
            info_items.insert(
                1, {"label": "Battery", "value": f"{self.batt_percent:.0f}%"}
            )

        storage = [
            {
                "label": "Memory",
                "value": round(self.mem_percent),
                "used": f"{self.mem_used:.1f} GB",
                "total": f"{self.mem_total:.1f} GB",
                "free": f"{max(self.mem_total - self.mem_used, 0.0):.1f} GB",
            },
            {
                "label": "Disk C:",
                "value": round(self.disk_percent),
                "used": f"{max(self.disk_total - self.disk_free, 0.0):.0f} GB",
                "total": f"{self.disk_total:.0f} GB",
                "free": f"{self.disk_free:.0f} GB",
            },
        ]

        blocks = [
            {
                "type": "controls",
                "style": "grid",
                "col": 0,
                "items": actions,
            },
            {
                "type": "kv",
                "col": 0,
                "items": info_items,
            },
            {
                "type": "cpu",
                "col": 1,
                "value": round(self.cpu),
                "temp": cpu_temp,
                "temp_name": "package" if cpu_temp is not None else "enable sensor",
                "threads": psutil.cpu_count(logical=True) or 0,
                "points": [round(v, 1) for v in self.history],
                "min": 0,
                "max": 100,
            },
            {
                "type": "storage",
                "col": 1,
                "items": storage,
            },
            {
                "type": "gpu",
                "col": 2,
                "temp": gpu_temp,
                "hot": None if self.gpu_hot is None else round(self.gpu_hot),
                "memory": None
                if self.gpu_memory is None
                else round(self.gpu_memory),
                "name": self.gpu_name
                or ("GPU" if gpu_temp is not None else "unavailable"),
                "net": [
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
