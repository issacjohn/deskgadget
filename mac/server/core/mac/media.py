"""Now playing + transport on macOS.

Three backends, tried in order, each optional:

1. ``nowplaying-cli`` — one binary that reads macOS' now-playing centre, so it
   works for Music, Spotify, browsers, VLC and anything else that reports a
   media session. Installed with ``brew install nowplaying-cli``.
2. AppleScript against Music / Spotify — nothing to install, prompts once for
   Automation permission.
3. Nothing — the media page still shows volume controls.

No private frameworks are loaded, which is what keeps this working across macOS
10.15 through current instead of breaking on the next release.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

from ..paths import bundle_dirs
from . import osascript, run, which

log = logging.getLogger("deskgadget.mac.media")

_SEP = "\x1f"

#: track key -> served artwork URL, plus a retry clock for tracks without art
_art_cache: dict[str, str] = {}
_art_tried: dict[str, float] = {}
_APPS = (
    ("Spotify", "Spotify"),
    ("Music", "Apple Music"),
)

#: bundle id -> the name the phone shows
_BUNDLES = {
    "org.mozilla.firefox": "Firefox",
    "com.google.chrome": "Chrome",
    "com.microsoft.edgemac": "Edge",
    "com.apple.Music": "Apple Music",
    "com.apple.Safari": "Safari",
    "com.spotify.client": "Spotify",
    "com.brave.Browser": "Brave",
    "com.videolan.vlc": "VLC",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _nowplaying_bin() -> Optional[str]:
    return which("nowplaying-cli")


def _running(app: str) -> bool:
    result = run(["pgrep", "-x", app], timeout=4)
    return result.returncode == 0


def _save_art(data: bytes, art_dir: Optional[Path]) -> str:
    if art_dir is None or len(data) < 128:
        return ""
    digest = hashlib.sha1(data).hexdigest()[:12]
    ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
    path = art_dir / f"now-{digest}.{ext}"
    try:
        art_dir.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
            for old in art_dir.glob("now-*"):
                if old != path:
                    try:
                        old.unlink()
                    except OSError:
                        pass
    except OSError:
        return ""
    return f"/artwork/{path.name}"


def _download_art(url: str, art_dir: Optional[Path]) -> str:
    if not url or art_dir is None:
        return ""
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    cached = next(iter(art_dir.glob(f"now-{digest}.*")), None) if art_dir.exists() else None
    if cached:
        return f"/artwork/{cached.name}"
    try:
        import requests

        response = requests.get(url, timeout=10, headers={"User-Agent": "DeskGadget"})
        if response.status_code == 200 and response.content:
            return _save_art(response.content, art_dir)
    except Exception:
        log.debug("artwork download failed", exc_info=True)
    return ""


# --------------------------------------------------------------------------- #
# backend 0: bundled MediaRemote adapter (BSD-3, no Automation permission)
# --------------------------------------------------------------------------- #
def _adapter_paths() -> Optional[tuple[Path, Path]]:
    candidates: list[Path] = []
    try:
        for base in bundle_dirs():
            candidates.append(base / "mediaremote")
            candidates.append(base / "vendor" / "mediaremote")
    except Exception:
        pass
    # source checkouts keep it next to server/, not inside it
    try:
        candidates.append(Path(__file__).resolve().parents[3] / "vendor" / "mediaremote")
    except IndexError:
        pass
    for base in candidates:
        script = base / "mediaremote-adapter.pl"
        framework = base / "MediaRemoteAdapter.framework"
        if script.is_file() and framework.is_dir():
            return script, framework
    return None


def adapter_available() -> bool:
    return _adapter_paths() is not None


def transport_available() -> bool:
    """True when media transport needs no Automation prompt."""
    return adapter_available() or _nowplaying_bin() is not None


def _adapter_get(include_art: bool) -> Optional[dict]:
    pair = _adapter_paths()
    if pair is None:
        return None
    script, framework = pair
    args = [which("perl") or "/usr/bin/perl", str(script), str(framework), "get"]
    if not include_art:
        args.append("--no-artwork")
    result = run(args, timeout=20 if include_art else 12)
    if result.returncode != 0:
        return None
    try:
        data = json.loads((result.stdout or "").strip() or "null")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _adapter_snapshot(art_dir: Optional[Path]) -> Optional[dict]:
    data = _adapter_get(False)
    if not data or not str(data.get("title") or "").strip():
        return None

    title = str(data.get("title") or "").strip()
    artist = str(data.get("artist") or "").strip()
    album = str(data.get("album") or "").strip()
    bundle = str(data.get("bundleIdentifier") or "")
    try:
        position = float(data.get("elapsedTime") or 0)
    except (TypeError, ValueError):
        position = 0.0
    try:
        duration = float(data.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0

    artwork = ""
    if art_dir is not None:
        key = f"{title}|{artist}|{album}"
        artwork = _art_cache.get(key, "")
        # Artwork is a second, heavier call, so only when the track changes and
        # at most once every few seconds for players that load it lazily.
        if not artwork and time.time() - _art_tried.get(key, 0.0) > 8.0:
            _art_tried[key] = time.time()
            full = _adapter_get(True) or {}
            encoded = full.get("artworkData")
            if encoded:
                try:
                    raw = base64.b64decode(encoded)
                except Exception:
                    raw = b""
                artwork = _save_art(raw, art_dir)
                if artwork:
                    _art_cache.clear()
                    _art_cache[key] = artwork
                    if len(_art_tried) > 16:
                        _art_tried.clear()

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "source": _BUNDLES.get(bundle, ""),
        "playing": bool(data.get("playing")),
        "position": max(0.0, position),
        "duration": max(0.0, duration),
        "artwork": artwork,
    }


def _adapter_send(action: str, seconds: float = 0.0) -> bool:
    pair = _adapter_paths()
    if pair is None:
        return False
    script, framework = pair
    perl = which("perl") or "/usr/bin/perl"
    if action == "seek":
        args = [perl, str(script), str(framework), "seek", str(max(0.0, float(seconds)))]
    else:
        command_id = {"play_pause": "2", "next": "4", "prev": "5"}.get(action)
        if command_id is None:
            return False
        args = [perl, str(script), str(framework), "send", command_id]
    return run(args, timeout=10).returncode == 0


# --------------------------------------------------------------------------- #
# backend 1: nowplaying-cli (any player)
# --------------------------------------------------------------------------- #
def _snapshot_nowplaying(art_dir: Optional[Path]) -> Optional[dict]:
    binary = _nowplaying_bin()
    if not binary:
        return None
    result = run(
        [binary, "get", "title", "artist", "album", "duration", "elapsedTime", "playbackRate"],
        timeout=6,
    )
    if result.returncode != 0:
        return None
    lines = (result.stdout or "").splitlines()
    if not lines or not lines[0].strip() or lines[0].strip().lower() in ("null", "(null)"):
        return None

    def value(index: int) -> str:
        if index >= len(lines):
            return ""
        text = lines[index].strip()
        return "" if text.lower() in ("null", "(null)", "none") else text

    title = value(0)
    if not title:
        return None
    try:
        duration = float(value(3) or 0)
    except ValueError:
        duration = 0.0
    try:
        position = float(value(4) or 0)
    except ValueError:
        position = 0.0
    try:
        rate = float(value(5) or 0)
    except ValueError:
        rate = 0.0
    return {
        "title": title,
        "artist": value(1),
        "album": value(2),
        "source": "Now Playing",
        "playing": rate > 0,
        "position": max(0.0, position),
        "duration": max(0.0, duration),
        "artwork": "",
    }


# --------------------------------------------------------------------------- #
# backend 2: AppleScript (Music / Spotify)
# --------------------------------------------------------------------------- #
_SPOTIFY_SCRIPT = """
tell application "Spotify"
    try
        if player state is stopped then return ""
        set t to name of current track
        set a to artist of current track
        set al to album of current track
        set d to (duration of current track) / 1000
        set p to player position
        set s to (player state as text)
        set au to artwork url of current track
        set AppleScript's text item delimiters to (ASCII character 31)
        return {t, a, al, (d as text), (p as text), s, au} as text
    on error
        return ""
    end try
end tell
"""

_MUSIC_SCRIPT = """
tell application "Music"
    try
        if player state is stopped then return ""
        set t to name of current track
        set a to artist of current track
        set al to album of current track
        set d to duration of current track
        set p to player position
        set s to (player state as text)
        set AppleScript's text item delimiters to (ASCII character 31)
        return {t, a, al, (d as text), (p as text), s, ""} as text
    on error
        return ""
    end try
end tell
"""


def _snapshot_script(app: str, script: str, source: str, art_dir: Optional[Path]) -> Optional[dict]:
    if not _running(app):
        return None
    text = osascript(script, timeout=8)
    if not text:
        return None
    parts = text.split(_SEP)
    if len(parts) < 6 or not parts[0].strip():
        return None
    try:
        duration = float(parts[3])
    except ValueError:
        duration = 0.0
    try:
        position = float(parts[4])
    except ValueError:
        position = 0.0
    artwork = _download_art(parts[6].strip(), art_dir) if len(parts) > 6 else ""
    return {
        "title": parts[0].strip(),
        "artist": parts[1].strip(),
        "album": parts[2].strip(),
        "source": source,
        "playing": parts[5].strip().lower() == "playing",
        "position": max(0.0, position),
        "duration": max(0.0, duration),
        "artwork": artwork,
    }


def _snapshot_applescript(art_dir: Optional[Path]) -> Optional[dict]:
    for app, source in _APPS:
        if not _running(app):
            continue
        if app == "Spotify":
            snap = _snapshot_script(app, _SPOTIFY_SCRIPT, source, art_dir)
        else:
            snap = _snapshot_script(app, _MUSIC_SCRIPT, source, art_dir)
        if snap:
            return snap
    return None


# --------------------------------------------------------------------------- #
# public API (same shape as the Windows SMTC module)
# --------------------------------------------------------------------------- #
def snapshot(art_dir: Optional[Path] = None) -> Optional[dict]:
    """Current media session, or None. Safe from any thread."""
    for backend in (_adapter_snapshot, _snapshot_nowplaying, _snapshot_applescript):
        try:
            value = backend(art_dir)
        except Exception:
            log.debug("media backend failed", exc_info=True)
            value = None
        if value:
            return value
    return None


def _script_for(action: str) -> str:
    commands = {
        "play_pause": "playpause",
        "next": "next track",
        "prev": "previous track",
    }
    command = commands.get(action)
    if not command:
        return ""
    # one script for both players: whichever is running gets the command
    return f"""
on run
    if application "Spotify" is running then
        tell application "Spotify" to {command}
        return "ok"
    end if
    if application "Music" is running then
        tell application "Music" to {command}
        return "ok"
    end if
    return ""
end run
"""


def command(action: str) -> bool:
    """Play/pause, next or previous on whatever is playing."""
    if _adapter_send(action):
        return True
    binary = _nowplaying_bin()
    if binary:
        mapping = {"play_pause": "togglePlayPause", "next": "nextTrack", "prev": "previousTrack"}
        arg = mapping.get(action)
        if arg and run([binary, arg], timeout=6).returncode == 0:
            return True
    script = _script_for(action)
    if script and osascript(script, timeout=8):
        return True
    return False


def seek(seconds: float) -> bool:
    seconds = max(0.0, float(seconds))
    if _adapter_send("seek", seconds):
        return True
    binary = _nowplaying_bin()
    if binary and run([binary, "seek", str(seconds)], timeout=6).returncode == 0:
        return True
    script = f"""
on run
    if application "Spotify" is running then
        tell application "Spotify" to set player position to {seconds}
        return "ok"
    end if
    if application "Music" is running then
        tell application "Music" to set player position to {seconds}
        return "ok"
    end if
    return ""
end run
"""
    return bool(osascript(script, timeout=8))
