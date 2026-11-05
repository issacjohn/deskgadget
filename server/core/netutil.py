"""Network helpers: LAN address, mDNS advertising, adb reverse for USB mode."""
from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import threading
from typing import Optional

log = logging.getLogger("liquiddeck.net")

SERVICE_TYPE = "_liquiddeck._tcp.local."


def lan_ip() -> str:
    """Best-effort primary LAN IPv4 address (no traffic is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def lan_ips() -> list[str]:
    """Every usable IPv4 address, primary first.

    A phone on USB tethering sits on its own subnet and can only reach the
    address of the adapter on that link, while a PC with both Wi-Fi and
    Ethernet has two perfectly good addresses. Advertise them all so the
    client can try whichever one it can actually route to.
    """
    ordered: list[str] = []
    primary = lan_ip()
    if primary and primary != "127.0.0.1":
        ordered.append(primary)
    try:
        import psutil

        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if (
                    addr.family == socket.AF_INET
                    and addr.address
                    and not addr.address.startswith(("127.", "169.254."))
                    and addr.address not in ordered
                ):
                    ordered.append(addr.address)
    except Exception:
        pass
    return ordered or ["127.0.0.1"]


class Discovery:
    """Advertise the server over mDNS so the phone can find it automatically."""

    def __init__(self, port: int, name: str) -> None:
        self.port = port
        self.name = name
        self._zc = None
        self._info = None

    def start(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except Exception:
            log.warning("zeroconf not installed; discovery disabled")
            return

        def register() -> None:
            try:
                ips = lan_ips()
                self._info = ServiceInfo(
                    SERVICE_TYPE,
                    f"{self.name}.{SERVICE_TYPE}",
                    addresses=[socket.inet_aton(ip) for ip in ips],
                    port=self.port,
                    properties={"v": "1", "name": self.name},
                    server=f"{socket.gethostname().lower()}.local.",
                )
                self._zc = Zeroconf()
                self._zc.register_service(self._info)
                log.info("mDNS advertising %s on %s:%s", self.name, ", ".join(ips), self.port)
            except Exception:
                log.exception("mDNS registration failed")

        # zeroconf blocks while advertising; keep it off the event loop
        threading.Thread(target=register, name="mdns", daemon=True).start()

    def stop(self) -> None:
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass


class Beacon(threading.Thread):
    """Answers LAN discovery probes with the server's current address.

    Works even when the router blocks mDNS, and always reports the *current*
    LAN IP, so a DHCP change is picked up on the next probe.
    """

    def __init__(self, port: int, server_name: str) -> None:
        super().__init__(name="beacon", daemon=True)
        self.port = port
        self.server_name = server_name
        self._stop = threading.Event()

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.settimeout(1.0)
        except Exception:
            log.exception("discovery beacon could not bind udp/%s", self.port)
            return
        log.info("discovery beacon listening on udp/%s", self.port)
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(256)
            except socket.timeout:
                continue
            except Exception:
                continue
            if not data.strip().lower().startswith(b"deskgadget"):
                continue
            try:
                reply = json.dumps(
                    {
                        "name": self.server_name,
                        "ip": lan_ip(),
                        "ips": lan_ips(),
                        "port": self.port,
                    }
                ).encode("utf-8")
                sock.sendto(reply, addr)
            except Exception:
                pass
        sock.close()

    def stop(self) -> None:
        self._stop.set()


class AdbBridge:
    """Keeps ``adb reverse tcp:PORT tcp:PORT`` alive for every USB device.

    With this in place the phone can reach the server at 127.0.0.1:PORT over the
    cable, with no Wi-Fi involved.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self.adb = shutil.which("adb")
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.devices: list[str] = []

    def available(self) -> bool:
        return bool(self.adb)

    def _run(self, *args: str) -> str:
        if not self.adb:
            return ""
        try:
            out = subprocess.run(
                [self.adb, *args],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return (out.stdout or "") + (out.stderr or "")
        except Exception:
            return ""

    def start(self) -> None:
        if not self.adb:
            log.warning("adb not found; USB mode unavailable")
            return
        self._thread = threading.Thread(target=self._loop, name="adb-bridge", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._run("devices")
                serials = [
                    line.split("\t")[0]
                    for line in text.splitlines()
                    if "\tdevice" in line and not line.startswith("List of")
                ]
                changed = serials != self.devices
                self.devices = serials
                for serial in serials:
                    self._run("-s", serial, "reverse", f"tcp:{self.port}", f"tcp:{self.port}")
                if changed and serials:
                    log.info("USB devices bridged: %s", ", ".join(serials))
            except Exception:
                pass
            self._stop.wait(5)

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {"available": self.available(), "devices": self.devices}
