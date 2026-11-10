"""Wake-on-LAN: send a magic packet to another machine.

Targets are configured in the dashboard as `Name=AA:BB:CC:DD:EE:FF`, separated
by commas or newlines.
"""
from __future__ import annotations

import re
import socket
import logging

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.wol")

PORT = 9


def _magic(mac: str) -> bytes:
    clean = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(clean) != 12:
        raise ValueError(f"bad MAC: {mac}")
    payload = bytes.fromhex(clean)
    return b"\xff" * 6 + payload * 16


def _parse_targets(raw: str) -> list[dict]:
    out: list[dict] = []
    for chunk in re.split(r"[,\n;]+", raw or ""):
        entry = chunk.strip()
        if not entry:
            continue
        if "=" in entry:
            name, mac = entry.split("=", 1)
        else:
            name, mac = "", entry
        mac = mac.strip()
        if len(re.sub(r"[^0-9A-Fa-f]", "", mac)) != 12:
            continue
        out.append({"name": name.strip() or mac.upper(), "mac": mac})
    return out[:24]


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.sent_at: str = ""
        self.last: str = ""

    async def update(self) -> None:
        # nothing to poll: the page is built from settings
        return None

    async def on_action(self, action: str, payload: dict) -> None:
        if action != "wake":
            return
        mac = str(payload.get("id") or payload.get("url") or "")
        target = next((t for t in _parse_targets(str(self.settings.get("targets", "")))
                       if t["mac"] == mac), None)
        if target is None:
            await self.hub.notify("Unknown target")
            return
        broadcast = str(self.settings.get("broadcast") or "255.255.255.255")
        try:
            packet = _magic(mac)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.sendto(packet, (broadcast, PORT))
                sock.sendto(packet, (broadcast, 7))
            finally:
                sock.close()
            self.last = f"Sent to {target['name']}"
            await self.hub.notify(self.last)
        except Exception:
            log.exception("wake failed for %s", mac)
            self.last = "Could not send the packet"
            await self.hub.notify(self.last)
        self.push()

    def page(self) -> dict:
        targets = _parse_targets(str(self.settings.get("targets", "")))
        if not targets:
            return {
                "blocks": [
                    {
                        "type": "hero",
                        "label": "WAKE ON LAN",
                        "value": "0",
                        "unit": "",
                        "sub": "No targets yet",
                        "accent": self.accent,
                        "col": 0,
                    },
                    {
                        "type": "note",
                        "label": "SET UP",
                        "text": "In the dashboard, add a target as Name=MAC — for example NAS=AA:BB:CC:DD:EE:FF.",
                        "meta": "One magic packet per tap, over UDP 9",
                        "col": 1,
                    },
                ]
            }
        return {
            "blocks": [
                {
                    "type": "list",
                    "title": "WAKE A MACHINE",
                    "items": [
                        {
                            "id": t["mac"],
                            "title": t["name"],
                            "sub": t["mac"].upper(),
                            "value": "WAKE",
                            "action": "wake",
                        }
                        for t in targets
                    ],
                }
            ]
        }
