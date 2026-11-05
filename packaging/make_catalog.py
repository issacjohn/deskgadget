"""Regenerate catalog.json from the plugin manifests.

The dashboard's "Browse modules" sheet reads this file from GitHub, so it has to
be rebuilt whenever a module is added or its manifest changes.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "server" / "plugins"
OUT = ROOT / "catalog.json"

FIELDS = ("id", "name", "description", "version", "author", "accent")


def main() -> None:
    modules = []
    for manifest in sorted(PLUGINS.glob("*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {manifest}: {exc}")
            continue
        entry = {key: data.get(key, "") for key in FIELDS}
        entry["id"] = entry["id"] or manifest.parent.name
        entry["path"] = f"server/plugins/{manifest.parent.name}"
        entry["builtin"] = True
        modules.append(entry)

    OUT.write_text(
        json.dumps({"version": 1, "modules": modules}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} with {len(modules)} modules")


if __name__ == "__main__":
    main()
