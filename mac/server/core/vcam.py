"""Virtual camera on macOS.

There is no DirectShow here, so the Windows filter approach is replaced by the
one virtual camera macOS actually supports: OBS's CoreMediaIO plugin.

Two supported routes, both documented in MAC.md:

* **OBS Virtual Camera** — if OBS is installed, DeskGadget feeds it through
  ``pyvirtualcam`` (backend ``obs``); every conferencing app then sees
  "OBS Virtual Camera".
* **Media Source** — no extra Python package at all: add
  ``http://<mac>:8787/api/camera/stream`` as an OBS Media Source and start the
  virtual camera. This is the zero-dependency path and works on every macOS.

Unlike Windows, a single phone can own the camera at a time; macOS exposes one
OBS device, not one per phone.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

log = logging.getLogger("deskgadget.vcam")

DEVICE_NAME = "OBS Virtual Camera"
SLOTS = 1
PYVIRTUALCAM_BACKEND = "obs"
PASS_DEVICE = False
SETUP_URL = "https://obsproject.com/download"

_OBS_PLUGIN_DIRS = (
    Path("/Library/CoreMediaIO/Plug-Ins/DAL"),
    Path.home() / "Library/CoreMediaIO/Plug-Ins/DAL",
)


def _obs_plugin() -> Path | None:
    for base in _OBS_PLUGIN_DIRS:
        if not base.is_dir():
            continue
        for entry in base.glob("OBS-VirtualCam*.plugin"):
            return entry
    return None


def is_registered() -> bool:
    """Whether macOS has an OBS virtual camera for apps to pick."""
    return _obs_plugin() is not None


def feed_available() -> bool:
    """Whether we can push frames ourselves (pyvirtualcam present)."""
    try:
        return importlib.util.find_spec("pyvirtualcam") is not None
    except Exception:
        return False


def ensure() -> tuple[bool, str]:
    if not is_registered():
        return (
            False,
            "Install OBS Studio, open it once, and choose Start Virtual Camera. "
            "DeskGadget can also send the phone to OBS directly: add "
            "http://<this-mac>:8787/api/camera/stream as a Media Source.",
        )
    if not feed_available():
        return (
            True,
            "OBS Virtual Camera is installed. To feed it straight from DeskGadget "
            "run: .venv/bin/pip install pyvirtualcam  (or add "
            "http://<this-mac>:8787/api/camera/stream as an OBS Media Source).",
        )
    return True, "OBS Virtual Camera is ready."


def phone_name(label: str) -> str:
    clean = " ".join((label or "Phone").split())
    return f"{DEVICE_NAME} - {clean}"[:63]


def set_slot_name(slot: int, name: str) -> bool:
    # One OS-level device, and its name belongs to OBS. Nothing to rename.
    return False


def slot_name(slot: int) -> str:
    return DEVICE_NAME


def slot_friendly_name(slot: int) -> str:
    return DEVICE_NAME if slot == 0 else ""


def slot_clsid(slot: int) -> str:
    return ""


def registered_path() -> str:
    plugin = _obs_plugin()
    return str(plugin) if plugin else ""


def is_admin() -> bool:
    return False


def setup_hint() -> str:
    return ensure()[1]
