"""Module (plugin) base class and loader for DeskGadget.

Every plugin lives in server/plugins/<folder>/ with a manifest.json describing
how it appears in the dashboard, plus module.py exposing a ``Module`` subclass.

Modules are trusted, in-process code for now, but the contract is deliberately
narrow (start/stop/action/settings) so a supervisor can later run each one in a
separate process without changing plugin authors' code.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from . import paths

log = logging.getLogger("deskgadget.modules")

PROTOCOL_VERSION = 1


class Module:
    """Base class for a DeskGadget module."""

    #: overridden by manifest.json, kept here as safe defaults
    id: str = "unknown"
    name: str = "Unknown"
    version: str = "1.0.0"
    accent: str = "#7CE7FF"
    interval: float = 2.0
    default_enabled: bool = True
    settings_schema: dict[str, Any] = {}
    author: str = ""
    description: str = ""

    def __init__(self, hub, settings: dict[str, Any]):
        self.hub = hub
        self.settings = dict(self.settings_schema and {} or {})
        self.settings.update(settings or {})
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._page: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------
    async def on_start(self) -> None:
        """Called once when the module's update loop begins."""

    async def on_stop(self) -> None:
        """Called when the module stops."""

    async def update(self) -> None:
        """Refresh internal state. Called every ``interval`` seconds."""

    async def on_action(self, action: str, payload: dict[str, Any]) -> None:
        """Handle a control press from the phone."""

    async def on_settings(self) -> None:
        """Settings changed in the dashboard; rebuild anything that depends on them."""

    # -- page rendering ----------------------------------------------------
    def page(self) -> dict[str, Any]:
        raise NotImplementedError

    def render(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "module": self.id,
            "title": self.name,
            "accent": self.accent,
            "refreshable": bool(getattr(self, "refreshable", False)),
            "blocks": self.page().get("blocks", []),
        }

    def push(self) -> None:
        """Send the current page to every device that has this module enabled."""
        try:
            self.draw()
        except Exception:  # a broken plugin must not kill the loop
            log.error("render failed for %s\n%s", self.id, traceback.format_exc())

    def draw(self) -> None:
        self.hub.publish(self)

    # -- runner ------------------------------------------------------------
    async def _run(self) -> None:
        try:
            await self.on_start()
        except Exception:
            log.error("on_start failed for %s\n%s", self.id, traceback.format_exc())
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            started = loop.time()
            try:
                await self.update()
                self.push()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error("update failed for %s\n%s", self.id, traceback.format_exc())
            # fixed-rate: subtract the time the work took, so a slow sample
            # doesn't push the whole schedule back
            elapsed = loop.time() - started
            delay = max(0.05, self.interval - elapsed)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name=f"module:{self.id}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        try:
            await self.on_stop()
        except Exception:
            log.error("on_stop failed for %s", self.id)


def _alias_core_modules() -> None:
    """Map `core.*` onto `server.core.*` so plugin and server share state."""
    import importlib

    for sub in ("", ".base", ".hub", ".launcher", ".netutil", ".paths", ".store", ".steam"):
        try:
            module = importlib.import_module("server.core" + sub)
        except Exception:
            continue
        sys.modules.setdefault("core" + sub, module)


def load_plugins(hub, settings_for, enabled_for) -> dict[str, Module]:
    """Load every plugin folder. Bad plugins are logged and skipped."""
    plugins_root = paths.plugins_dir()
    modules: dict[str, Module] = {}

    # Plugins are documented as `from core.base import Module`, but the server
    # itself imports `server.core.*`. Without aliasing, those are two distinct
    # module objects with separate state (e.g. the icon-source registry), so
    # make the short name point at the already-imported modules.
    _alias_core_modules()

    for folder in sorted(p for p in plugins_root.iterdir() if p.is_dir()):
        manifest_path = folder / "manifest.json"
        module_path = folder / "module.py"
        if not manifest_path.exists() or not module_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            mod_id = manifest["id"]
            spec = importlib.util.spec_from_file_location(f"deskgadget_plugin_{mod_id}", module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {module_path}")
            py_mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = py_mod
            # let plugins write `from core.base import Module` in both the repo
            # and the packaged build (where core lives next to this file)
            server_dir = str(Path(__file__).resolve().parent.parent)
            for entry in (server_dir, str(plugins_root.parent)):
                if entry not in sys.path:
                    sys.path.insert(0, entry)
            spec.loader.exec_module(py_mod)

            cls = getattr(py_mod, "Module", None)
            if cls is None:
                raise ImportError("module.py must expose a Module class")

            instance = cls(hub, settings_for(mod_id))
            instance.id = mod_id
            instance.name = manifest.get("name", mod_id)
            instance.version = manifest.get("version", "1.0.0")
            instance.accent = manifest.get("accent", instance.accent)
            instance.interval = float(manifest.get("interval", instance.interval))
            instance.default_enabled = bool(manifest.get("default_enabled", True))
            instance.settings_schema = manifest.get("settings", {}) or {}
            instance.author = manifest.get("author", "")
            instance.description = manifest.get("description", "")
            instance.enabled = enabled_for(mod_id, instance.default_enabled)
            modules[mod_id] = instance
            log.info("loaded plugin %s v%s", mod_id, instance.version)
        except Exception:
            log.error("failed to load plugin in %s\n%s", folder.name, traceback.format_exc())

    return modules
