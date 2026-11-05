"""Windows media session (SMTC): track, artist, artwork and transport.

`winrt-Windows.Media.Control` is the same API browser and Spotify expose to the
Windows media flyout, so it works for any app that registers a media session,
not just one player.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("liquiddeck.smtc")

_PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING

# AUMIDs are ugly; show the app people recognise.
_APP_NAMES = (
    ("spotify", "Spotify"),
    ("chrome", "Chrome"),
    ("msedge", "Edge"),
    ("firefox", "Firefox"),
    ("brave", "Brave"),
    ("opera", "Opera"),
    ("vlc", "VLC"),
    ("foobar", "foobar2000"),
    ("applemusic", "Apple Music"),
    ("zune", "Media Player"),
    ("308046b0af4a39cb", "Edge"),
    ("microsoft.zunemusic", "Media Player"),
    ("tidal", "TIDAL"),
    ("deezer", "Deezer"),
    ("youtube", "YouTube"),
)


def _run(coro):
    """Run a WinRT coroutine from a worker thread (never from the event loop)."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _app_name(aumid: str) -> str:
    low = (aumid or "").lower()
    for needle, name in _APP_NAMES:
        if needle in low:
            return name
    return ""


async def _manager():
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return await Manager.request_async()


async def _thumb_bytes(ref) -> bytes:
    from winrt.windows.storage.streams import DataReader

    stream = await ref.open_read_async()
    size = int(stream.size)
    if size <= 0 or size > 8_000_000:
        return b""
    reader = DataReader(stream)
    await reader.load_async(size)
    # read_bytes() into a fresh Buffer comes back empty; read_buffer() is the
    # call that actually returns the loaded bytes
    buffer = reader.read_buffer(size)
    return bytes(buffer)


def _save_art(data: bytes, art_dir: Path) -> str:
    if len(data) < 128:
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


async def _snapshot(art_dir: Optional[Path]) -> Optional[dict]:
    mgr = await _manager()
    # prefer whatever is actually playing: a paused leftover session (a closed
    # browser tab, say) would otherwise mask the thing you are listening to
    session = None
    try:
        for candidate in mgr.get_sessions():
            try:
                if int(candidate.get_playback_info().playback_status) == _PLAYING:
                    session = candidate
                    break
            except Exception:
                continue
    except Exception:
        session = None
    if session is None:
        session = mgr.get_current_session()
    if session is None:
        return None
    info = await session.try_get_media_properties_async()
    timeline = session.get_timeline_properties()
    playback = session.get_playback_info()
    try:
        status = int(playback.playback_status)
    except Exception:
        status = 0

    artwork = ""
    if art_dir is not None and info.thumbnail is not None:
        try:
            artwork = _save_art(await _thumb_bytes(info.thumbnail), art_dir)
        except Exception:
            artwork = ""

    position = timeline.position.total_seconds() if timeline.position else 0.0
    duration = timeline.end_time.total_seconds() if timeline.end_time else 0.0
    return {
        "title": (info.title or "").strip(),
        "artist": (info.artist or "").strip(),
        "album": (info.album_title or "").strip(),
        "source": _app_name(session.source_app_user_model_id),
        "playing": status == _PLAYING,
        "position": max(0.0, position),
        "duration": max(0.0, duration),
        "artwork": artwork,
    }


def snapshot(art_dir: Optional[Path] = None) -> Optional[dict]:
    """Current session, or None when nothing is playing. Safe from any thread."""
    try:
        return _run(_snapshot(art_dir))
    except Exception:
        log.debug("smtc snapshot failed", exc_info=True)
        return None


async def _command(action: str) -> bool:
    mgr = await _manager()
    session = mgr.get_current_session()
    if session is None:
        return False
    if action == "play_pause":
        return bool(await session.try_toggle_play_pause_async())
    if action == "next":
        return bool(await session.try_skip_next_async())
    if action == "prev":
        return bool(await session.try_skip_previous_async())
    return False


def command(action: str) -> bool:
    """Play/pause, next or previous on the active session."""
    try:
        return _run(_command(action))
    except Exception:
        log.debug("smtc command failed", exc_info=True)
        return False


async def _seek(seconds: float) -> bool:
    mgr = await _manager()
    session = mgr.get_current_session()
    if session is None:
        return False
    return bool(
        await session.try_change_playback_position_async(
            timedelta(seconds=max(0.0, seconds))
        )
    )


def seek(seconds: float) -> bool:
    try:
        return _run(_seek(seconds))
    except Exception:
        log.debug("smtc seek failed", exc_info=True)
        return False
