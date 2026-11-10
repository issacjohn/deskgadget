"""Steam library discovery: installed games, launch URIs and cover art."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

log = logging.getLogger("deskgadget.steam")

# runtimes and redistributables that are not games
SKIP_APPIDS = {
    228980,   # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime
    1391110,  # Steam Linux Runtime - Soldier
    1493710,  # Proton Experimental
    2180100,  # Proton Hotfix
    1580130,  # Proton EasyAntiCheat Runtime
    1826330,  # Proton BattlEye Runtime
}

_PATH_RE = re.compile(r'"path"\s+"([^"]+)"')


def steam_root() -> Path | None:
    candidates: list[Path] = [
        Path.home() / "Library" / "Application Support" / "Steam",
        Path.home() / ".steam" / "steam",
        Path("/Applications/Steam.app/Contents/MacOS"),
    ]
    # Windows installs keep a registry pointer; harmless to try, and it keeps
    # this module usable if someone drops the server onto a SMB share.
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        value, _ = winreg.QueryValueEx(key, "SteamPath")
        candidates.append(Path(value))
    except Exception:
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            candidates.append(Path(base) / "Steam")
    for candidate in candidates:
        if (candidate / "steamapps").is_dir():
            return candidate
    return None


def _libraries(root: Path) -> list[Path]:
    libraries = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for match in _PATH_RE.finditer(text):
                raw = match.group(1).replace("\\\\", "\\")
                path = Path(os.path.expanduser(raw))
                if path not in libraries:
                    libraries.append(path)
        except Exception:
            log.warning("could not parse libraryfolders.vdf")
    return libraries


def cover_url(appid: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg"


def header_url(appid: int) -> str:
    return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"


def launch_uri(appid: int) -> str:
    return f"steam://rungameid/{appid}"


def installed_games() -> list[dict]:
    """Every fully installed Steam game across all libraries."""
    root = steam_root()
    if root is None:
        return []

    games: list[dict] = []
    seen: set[int] = set()

    for library in _libraries(root):
        apps_dir = library / "steamapps"
        if not apps_dir.is_dir():
            continue
        for acf in apps_dir.glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            appid_m = re.search(r'"appid"\s+"(\d+)"', text)
            name_m = re.search(r'"name"\s+"([^"]+)"', text)
            state_m = re.search(r'"StateFlags"\s+"(\d+)"', text)
            if not appid_m or not name_m:
                continue
            appid = int(appid_m.group(1))
            if appid in SKIP_APPIDS or appid in seen:
                continue
            if state_m and state_m.group(1) not in ("4", "6"):
                continue  # not fully installed
            seen.add(appid)
            games.append(
                {
                    "appid": appid,
                    "name": name_m.group(1),
                    "icon_url": cover_url(appid),
                    "fallback_url": header_url(appid),
                }
            )

    games.sort(key=lambda g: g["name"].lower())
    return games
