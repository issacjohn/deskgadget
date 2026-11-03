"""Windows app discovery, launching, and icon extraction.

Icons are pulled straight out of the executable / shortcut with .NET's
System.Drawing, cached as PNGs in server/data/icons, and served to the phone.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path

import requests

log = logging.getLogger("liquiddeck.launcher")

from .paths import state_dir

ICON_DIR = state_dir() / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

START_MENUS = [
    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]

_PS_ICON_SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "tools" / "extract_icon.ps1"


def icon_key(path: str) -> str:
    return hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16]


def ensure_icon(key: str) -> Path | None:
    """Return a cached icon for a key, extracting or downloading it if missing."""
    if not key.isalnum():
        return None
    cached = _cached_icon(key)
    if cached:
        return cached

    url = _icon_urls.get(key)
    if url:
        return _download_icon(key, url, None)

    source = _icon_sources.get(key)
    if not source or "://" in source or not Path(source).exists():
        return None
    out = ICON_DIR / f"{key}.png"
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_PS_ICON_SCRIPT),
                "-src",
                source,
                "-out",
                str(out),
            ],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        log.exception("icon extraction failed for %s", source)
        return None
    if out.exists() and out.stat().st_size > 0:
        return out
    return None


# key -> source executable, populated by list_installed_apps and by the
# shortcuts module (so icons for user-picked files still resolve).
_icon_sources: dict[str, str] = {}
_icon_urls: dict[str, str] = {}
ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def register_icon_source(path: str) -> str:
    key = icon_key(path)
    _icon_sources[key] = path
    return key


def register_icon_url(url: str) -> str:
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    _icon_urls[key] = url
    return key


def _cached_icon(key: str) -> Path | None:
    for ext in ICON_EXTS:
        path = ICON_DIR / f"{key}{ext}"
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _download_icon(key: str, url: str, fallback: str | None) -> Path | None:
    for candidate in [url] + ([fallback] if fallback else []):
        try:
            r = requests.get(candidate, timeout=15, headers={"User-Agent": "DESKGadget"})
            if r.status_code == 200 and r.content:
                ext = ".png" if candidate.lower().endswith(".png") else ".jpg"
                out = ICON_DIR / f"{key}{ext}"
                out.write_bytes(r.content)
                return out
        except Exception:
            log.warning("icon download failed: %s", candidate)
    return None


def list_installed_apps() -> list[dict]:
    """Enumerate Start Menu shortcuts (.lnk) and bare executables."""
    apps: list[dict] = []
    seen: set[str] = set()
    for root in START_MENUS:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            name = lnk.stem
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            apps.append(
                {
                    "name": name,
                    "path": str(lnk),
                    "icon": register_icon_source(str(lnk)),
                }
            )
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def launch(path: str) -> tuple[bool, str]:
    if not path:
        return False, "empty path"
    if "://" in path:  # steam://, or any other shell protocol
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return True, "launched"
        except Exception as exc:
            return False, str(exc)
    target = Path(path)
    if not target.exists():
        return False, f"not found: {path}"
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return True, "launched"
    except Exception as exc:
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(target)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True, "launched"
        except Exception:
            return False, str(exc)
