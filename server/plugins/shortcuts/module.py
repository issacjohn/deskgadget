"""Shortcuts module: user-editable app launcher with auto-fetched icons.

Detected Steam games are merged in automatically (cover art downloaded from the
Steam CDN). Removing a game in the dashboard hides it for good via `hidden`.
"""
from __future__ import annotations

import logging
import time

from core import steam
from core.base import Module as BaseModule
from core.launcher import launch, register_icon_source, register_icon_url

log = logging.getLogger("liquiddeck.shortcuts")

RESCAN_SECONDS = 300


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self._last_scan = 0.0
        self._register()

    def _items(self) -> list[dict]:
        items = self.settings.get("items") or []
        return [i for i in items if i.get("path")]

    def _register(self) -> None:
        # re-register every time: the registry lives in memory, so a restart
        # must rebuild it even though the icon keys are already stored
        for item in self._items():
            path = item.get("path", "")
            if "://" in path:
                try:
                    appid = int(path.rsplit("/", 1)[-1])
                except (ValueError, IndexError):
                    continue
                item["icon"] = register_icon_url(steam.cover_url(appid))
            else:
                item["icon"] = register_icon_source(path)

    async def on_start(self) -> None:
        self._sync_steam()

    async def on_settings(self) -> None:
        self._sync_steam()
        self._register()
        self.push()

    async def update(self) -> None:
        if time.time() - self._last_scan < RESCAN_SECONDS:
            return
        if self._sync_steam():
            self.push()

    def _sync_steam(self) -> bool:
        self._last_scan = time.time()
        try:
            games = steam.installed_games()
        except Exception:
            log.exception("steam scan failed")
            return False
        if not games:
            return False

        items = list(self.settings.get("items") or [])
        hidden = set(self.settings.get("hidden") or [])
        known = set(self.settings.get("known_steam") or [])
        current_ids = {str(i.get("id")) for i in items}

        # a game we added before but that is now missing was removed on purpose
        removed = {sid for sid in known if sid not in current_ids and sid not in hidden}
        hidden |= removed

        added = False
        for game in games:
            sid = f"steam-{game['appid']}"
            if sid in current_ids or sid in hidden:
                continue
            items.append(
                {
                    "id": sid,
                    "label": game["name"],
                    "path": steam.launch_uri(game["appid"]),
                    "icon": register_icon_url(game["icon_url"]),
                    "source": "steam",
                }
            )
            known.add(sid)
            added = True

        if added or removed:
            self.settings["items"] = items
            self.settings["hidden"] = sorted(hidden)
            self.settings["known_steam"] = sorted(known)
            try:
                self.hub.store.set_module_settings(self.id, self.settings)
            except Exception:
                log.warning("could not persist steam shortcuts")
            if added:
                log.info("added %d steam game(s)", len(items) - len(current_ids))
        return added

    async def on_action(self, action: str, payload: dict) -> None:
        if action != "launch":
            return
        target = str(payload.get("id", ""))
        for item in self._items():
            if item.get("id") == target or item.get("path") == target:
                ok, message = launch(item["path"])
                if ok:
                    await self.hub.notify(f"Launched {item.get('label') or 'app'}")
                else:
                    await self.hub.notify(f"Could not launch: {message}")
                return

    def page(self) -> dict:
        items = []
        for item in self._items():
            items.append(
                {
                    "id": item.get("id") or item["path"],
                    "label": item.get("label") or item["path"].split("\\")[-1].replace(".lnk", ""),
                    "icon": f"/icons/{item.get('icon')}",
                    "path": item["path"],
                }
            )
        blocks = [
            {
                "type": "shortcuts",
                "title": "LAUNCH ON PC",
                "columns": int(self.settings.get("columns", 3)),
                "items": items,
            }
        ]
        if not items:
            blocks = [
                {
                    "type": "hero",
                    "label": "SHORTCUTS",
                    "value": "0",
                    "unit": "",
                    "sub": "Add shortcuts in the dashboard",
                }
            ]
        return {"blocks": blocks}
