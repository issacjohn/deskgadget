"""macOS app discovery, launching and icon extraction.

Icons come out of the bundle's ``.icns`` with ``sips`` — the same converter the
Finder previews use — so no PowerShell, no .NET and no external dependency. If
an app keeps its icon somewhere exotic we ask NSWorkspace through pyobjc, and
if pyobjc is missing the phone simply draws its placeholder.
"""
from __future__ import annotations

import hashlib
import logging
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import requests

from .mac import NO_WINDOW
from .paths import state_dir

log = logging.getLogger("deskgadget.launcher")

ICON_DIR = state_dir() / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

#: where macOS puts user-facing apps; scanned to a depth of two so suites like
#: "Adobe Photoshop 2025/Adobe Photoshop.app" are not missed
APP_DIRS = [
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]

ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def icon_key(path: str) -> str:
    return hashlib.sha1(path.lower().encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# icon sources
# --------------------------------------------------------------------------- #
_icon_sources: dict[str, str] = {}
_icon_urls: dict[str, str] = {}


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


def _sips(source: Path, out: Path, size: int = 128) -> bool:
    tool = shutil.which("sips") or "/usr/bin/sips"
    try:
        result = subprocess.run(
            [tool, "-s", "format", "png", "-Z", str(size), str(source), "--out", str(out)],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=NO_WINDOW,
        )
        return result.returncode == 0 and out.exists() and out.stat().st_size > 0
    except Exception:
        return False


def _bundle_icns(app: Path) -> Path | None:
    """The .icns a bundle points at, with sensible fallbacks."""
    info = app / "Contents" / "Info.plist"
    if info.exists():
        try:
            with info.open("rb") as handle:
                meta = plistlib.load(handle)
            name = str(meta.get("CFBundleIconFile") or "")
            if name:
                candidate = app / "Contents" / "Resources" / name
                if candidate.suffix.lower() != ".icns":
                    candidate = candidate.with_suffix(".icns")
                if candidate.exists():
                    return candidate
        except Exception:
            log.debug("could not read %s", info, exc_info=True)
    resources = app / "Contents" / "Resources"
    if resources.is_dir():
        icons = sorted(resources.glob("*.icns"), key=lambda p: p.stat().st_size, reverse=True)
        if icons:
            return icons[0]
    return None


def _nsicon(source: Path, out: Path) -> bool:
    """Ask NSWorkspace for the rendered icon (needs pyobjc, optional)."""
    try:
        import AppKit

        image = AppKit.NSWorkspace.sharedWorkspace().iconForFile_(str(source))
        if image is None:
            return False
        image.setSize_((128.0, 128.0))
        tiff = image.TIFFRepresentation()
        rep = AppKit.NSBitmapImageRep.imageRepWithData_(tiff)
        png = rep.representationUsingType_properties_(4, {})  # NSBitmapImageFileTypePNG
        out.write_bytes(bytes(png))
        return out.exists() and out.stat().st_size > 0
    except Exception:
        return False


def ensure_icon(key: str) -> Path | None:
    if not key.isalnum():
        return None
    cached = _cached_icon(key)
    if cached:
        return cached

    url = _icon_urls.get(key)
    if url:
        return _download_icon(key, url, None)

    source = _icon_sources.get(key)
    if not source:
        return None
    path = Path(source)
    out = ICON_DIR / f"{key}.png"
    if path.is_dir() and path.suffix.lower() == ".app":
        icns = _bundle_icns(path)
        if icns and _sips(icns, out):
            return out
        if _nsicon(path, out):
            return out
        return None
    if path.suffix.lower() == ".icns" and path.exists():
        return out if _sips(path, out) else None
    if path.exists() and _nsicon(path, out):
        return out
    return None


def _download_icon(key: str, url: str, fallback: str | None) -> Path | None:
    for candidate in [url] + ([fallback] if fallback else []):
        try:
            response = requests.get(candidate, timeout=15, headers={"User-Agent": "DeskGadget"})
            if response.status_code == 200 and response.content:
                ext = ".png" if candidate.lower().endswith(".png") else ".jpg"
                out = ICON_DIR / f"{key}{ext}"
                out.write_bytes(response.content)
                return out
        except Exception:
            log.warning("icon download failed: %s", candidate)
    return None


# --------------------------------------------------------------------------- #
# app catalogue
# --------------------------------------------------------------------------- #
def _apps_in(root: Path, depth: int = 2) -> list[Path]:
    found: list[Path] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and entry.suffix.lower() == ".app":
            found.append(entry)
        elif entry.is_dir() and depth > 1:
            found.extend(_apps_in(entry, depth - 1))
    return found


def list_installed_apps() -> list[dict]:
    """Every .app bundle a normal user can launch, deduplicated by name."""
    apps: list[dict] = []
    seen: set[str] = set()
    for root in APP_DIRS:
        if not root.exists():
            continue
        for bundle in _apps_in(root):
            name = bundle.stem
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            apps.append(
                {
                    "name": name,
                    "path": str(bundle),
                    "icon": register_icon_source(str(bundle)),
                }
            )
    apps.sort(key=lambda item: item["name"].lower())
    return apps


def launch(path: str) -> tuple[bool, str]:
    """Open an app, file, folder or URL through LaunchServices."""
    if not path:
        return False, "empty path"
    target = str(path)
    if "://" in target:
        result = subprocess.run(
            ["open", target], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW
        )
        return (result.returncode == 0), ("launched" if result.returncode == 0 else (result.stderr or "").strip()[:160])

    candidate = Path(target).expanduser()
    if not candidate.exists():
        return False, f"not found: {target}"
    try:
        result = subprocess.run(
            ["open", str(candidate)],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=NO_WINDOW,
        )
        if result.returncode == 0:
            return True, "launched"
        # a bare executable is not a document: run it directly
        if candidate.is_file() and os.access(candidate, os.X_OK):
            subprocess.Popen([str(candidate)], start_new_session=True)
            return True, "launched"
        return False, (result.stderr or "").strip()[:160]
    except Exception as exc:
        return False, str(exc)[:160]
