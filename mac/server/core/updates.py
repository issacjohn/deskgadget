"""Desktop app updates from the public GitHub releases.

The Windows build has no background updater: the dashboard asks this module
whether a newer release exists, and *Update now* downloads the installer and
hands over to it. The installer already keeps `data/` and `plugins/`, so the
update is just "run the new setup".
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

try:  # imported as `server.core.updates` by the app, `core.updates` by plugins
    from .paths import app_dir
except ImportError:
    from paths import app_dir

REPO = "issacjohn/deskgadget"
ASSET_NAME = "DeskGadget-Setup.exe"
RELEASES = f"https://api.github.com/repos/{REPO}/releases"
LATEST = f"{RELEASES}/latest"
CACHE_SECONDS = 600

_cache: dict = {"key": None, "at": 0.0, "result": None}


def current_version() -> str:
    """The version bundled at build time (repo root or PyInstaller root)."""
    for path in (app_dir().parent / "VERSION", app_dir() / "VERSION"):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return "dev"


def _parts(version: str) -> tuple[list[int], str]:
    text = version.strip().lstrip("v")
    main, _, pre = text.partition("-")
    numbers: list[int] = []
    for bit in main.split("."):
        try:
            numbers.append(int(bit))
        except ValueError:
            numbers.append(0)
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[:3], pre


def _pre_key(pre: str) -> list[tuple[int, object]]:
    key: list[tuple[int, object]] = []
    for bit in re.split(r"[.\-]", pre):
        if not bit:
            continue
        key.append((0, int(bit)) if bit.isdigit() else (1, bit))
    return key


def is_newer(remote: str, current: str) -> bool:
    """1.3.9 > 1.3.8, 1.3.8 > 1.3.8-beta.7, beta.7 > beta.6."""
    remote_nums, remote_pre = _parts(remote)
    current_nums, current_pre = _parts(current)
    if remote_nums != current_nums:
        return remote_nums > current_nums
    if not remote_pre and current_pre:
        return True
    if remote_pre and not current_pre:
        return False
    if remote_pre == current_pre:
        return False
    return _pre_key(remote_pre) > _pre_key(current_pre)


def _fetch(beta: bool) -> list[dict]:
    if beta:
        response = requests.get(
            RELEASES,
            params={"per_page": 20},
            headers={"Accept": "application/vnd.github+json", "User-Agent": "DeskGadget"},
            timeout=12,
        )
    else:
        response = requests.get(
            LATEST,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "DeskGadget"},
            timeout=12,
        )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else [data]


def _installer(release: dict) -> dict | None:
    for asset in release.get("assets") or []:
        if asset.get("name") == ASSET_NAME:
            return asset
    return None


def check(*, beta: bool = False, force: bool = False) -> dict:
    """Ask GitHub for the newest release that is newer than this build."""
    current = current_version()
    if sys.platform != "win32":
        # The public release feed only carries the Windows installer. The macOS
        # build is updated by re-running mac/install.command, so never nag.
        return {
            "current": current,
            "latest": current,
            "available": False,
            "notes": "",
            "url": "",
            "size": 0,
            "prerelease": False,
            "can_install": False,
            "managed": "mac",
        }
    key = (beta, current)
    if not force and _cache["key"] == key and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["result"]

    result = {
        "current": current,
        "latest": current,
        "available": False,
        "notes": "",
        "url": "",
        "size": 0,
        "prerelease": False,
        "can_install": bool(getattr(sys, "frozen", False)) and sys.platform == "win32",
    }
    try:
        for release in _fetch(beta):
            if release.get("draft"):
                continue
            tag = str(release.get("tag_name", "")).removeprefix("v").strip()
            if not tag or not is_newer(tag, current):
                continue
            asset = _installer(release)
            if asset is None:
                continue
            result.update(
                latest=tag,
                available=True,
                notes=str(release.get("body", "")),
                url=str(asset.get("browser_download_url", "")),
                size=int(asset.get("size", 0)),
                prerelease=bool(release.get("prerelease")),
            )
            break
    except Exception as exc:  # offline, rate limit, DNS
        result["error"] = str(exc)

    _cache.update(key=key, at=time.time(), result=result)
    return result


# --------------------------------------------------------------------------- #
# download / apply
# --------------------------------------------------------------------------- #
_dl: dict = {
    "state": "idle",  # idle | downloading | ready | error
    "received": 0,
    "total": 0,
    "version": "",
    "error": "",
    "path": "",
}
_dl_lock = threading.Lock()


def progress() -> dict:
    with _dl_lock:
        data = dict(_dl)
    data.pop("path", None)
    return data


def _worker(url: str, target: Path, total: int) -> None:
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(1 << 16):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    with _dl_lock:
                        _dl["received"] += len(chunk)
        with _dl_lock:
            _dl.update(state="ready", path=str(target))
            if not _dl["total"]:
                _dl["total"] = _dl["received"]
    except Exception as exc:
        with _dl_lock:
            _dl.update(state="error", error=str(exc))


def download(*, beta: bool = False) -> tuple[bool, str, dict]:
    """Start downloading the installer in the background."""
    if sys.platform != "win32":
        return (
            False,
            "macOS builds update with mac/install.command; there is nothing to download.",
            progress(),
        )
    with _dl_lock:
        if _dl["state"] == "downloading":
            return True, "Downloading.", dict(_dl)

    result = check(beta=beta, force=True)
    if not result.get("available") or not result.get("url"):
        return False, "No newer build available.", result

    target = Path(tempfile.gettempdir()) / f"DeskGadget-Setup-{result['latest']}.exe"
    total = int(result.get("size") or 0)
    with _dl_lock:
        _dl.update(
            state="downloading",
            received=0,
            total=total,
            version=str(result["latest"]),
            error="",
            path=str(target),
        )
    threading.Thread(
        target=_worker,
        args=(str(result["url"]), target, total),
        name="update-download",
        daemon=True,
    ).start()
    return True, "Downloading.", progress()


def apply() -> tuple[bool, str]:
    """Run the downloaded installer; the caller exits the app afterwards."""
    if sys.platform != "win32":
        return False, "Windows only."
    with _dl_lock:
        ready = _dl["state"] == "ready"
        path = Path(_dl["path"]) if _dl["path"] else None
    if not ready or path is None or not path.exists():
        return False, "The update has not finished downloading yet."
    if not getattr(sys, "frozen", False):
        return False, "Updates only run in the installed app."
    try:
        # The app exits right after this call, so the installer must not inherit
        # our handles (a closed stdout kills a console build before it starts).
        flags = 0
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(path)],
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as exc:
        return False, f"Could not start the installer: {exc}"
    return True, "Installing — DeskGadget will restart."
