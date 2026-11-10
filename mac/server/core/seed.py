"""Seed the writable data folder from the bundled app.

A PyInstaller app is read-only (and may be translocated by Gatekeeper), so
plugins, the dashboard and templates are copied into
``~/Library/Application Support/DeskGadget`` on first launch. On later launches
the marker file skips unchanged work; when the app version changes, static
assets are refreshed and new bundled modules are added.

User intent is preserved:
* an installed module is never overwritten,
* a module in ``plugins_removed/`` is never re-added,
* ``data/state.json`` (devices, themes, settings) is never touched.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from . import paths

log = logging.getLogger("deskgadget.seed")

MARKER = ".bundle-version"
_IGNORE = {"__pycache__", ".DS_Store"}


def _version(bundle: Path) -> str:
    for candidate in (bundle / "VERSION", bundle.parent / "VERSION"):
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return "dev"


def _copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name in _IGNORE:
            continue
        destination = target / entry.name
        if entry.is_dir():
            _copy_tree(entry, destination)
        else:
            try:
                shutil.copy2(entry, destination)
            except OSError:
                log.debug("could not copy %s", entry, exc_info=True)


def ensure(force: bool = False) -> None:
    """Copy bundled assets into the data folder when needed."""
    if not paths.is_frozen() and not force:
        return

    bundle = paths.bundle_dir()
    data = paths.data_dir()
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.exception("cannot create %s", data)
        return

    version = _version(bundle)
    marker = data / MARKER
    try:
        current = marker.read_text(encoding="utf-8").strip()
    except OSError:
        current = ""

    fresh = not (data / "plugins").is_dir()

    # Dashboard and templates are static assets: in a bundled app refresh them
    # on every launch, so a dashboard fix does not require a version bump.
    if force or fresh or current != version or paths.is_frozen():
        _copy_tree(bundle / "dashboard", data / "dashboard")
        _copy_tree(bundle / "templates", data / "templates")
        log.debug("seeded dashboard and templates from %s", bundle)

    # modules: add the ones this build knows about, respect removals
    plugins_root = data / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    removed_root = data / "plugins_removed"
    bundled = bundle / "plugins"
    if bundled.is_dir():
        for source in sorted(bundled.iterdir()):
            if not source.is_dir() or source.name in _IGNORE:
                continue
            target = plugins_root / source.name
            if target.exists() or (removed_root / source.name).exists():
                continue
            _copy_tree(source, target)
            log.info("installed bundled module: %s", source.name)

    try:
        marker.write_text(version, encoding="utf-8")
    except OSError:
        log.debug("could not write version marker", exc_info=True)
