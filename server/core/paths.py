"""Filesystem layout, so the same code runs from the repo and from the EXE.

In development `data_dir()` is the `server/` folder, so plugins and state stay
in the repo. The packaged launcher copies assets into
`%LOCALAPPDATA%\\DESKGadget` and points DESKGADGET_DATA there, which keeps the
install directory read-only and lets users drop in their own modules.
"""
from __future__ import annotations

import os
from pathlib import Path


def app_dir() -> Path:
    return Path(os.environ.get("DESKGADGET_ROOT") or Path(__file__).resolve().parent.parent)


def data_dir() -> Path:
    return Path(os.environ.get("DESKGADGET_DATA") or app_dir())


def plugins_dir() -> Path:
    return data_dir() / "plugins"


def dashboard_dir() -> Path:
    return data_dir() / "dashboard"


def templates_dir() -> Path:
    return data_dir() / "templates"


def state_dir() -> Path:
    path = data_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path
