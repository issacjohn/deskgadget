"""Clipboard bridge using the tools every macOS ships with.

``pbpaste``/``pbcopy`` are the supported interface for background processes and
handle UTF-8, RTF and images (we only need text). No TCC prompt, no framework.
"""
from __future__ import annotations

import logging

from . import run

log = logging.getLogger("deskgadget.mac.clipboard")


def read() -> str:
    result = run(["pbpaste"], timeout=5)
    if result.returncode != 0:
        log.debug("pbpaste failed: %s", (result.stderr or "")[:120])
        return ""
    return result.stdout or ""


def write(text: str) -> bool:
    try:
        result = run(["pbcopy"], input_text=str(text), timeout=5)
        return result.returncode == 0
    except Exception:
        log.debug("pbcopy failed", exc_info=True)
        return False
