# Writing a DeskGadget module

A module is a folder with two files. Nothing else is required, and no app
release is needed — the phone renders whatever blocks you return.

```
server/plugins/hello/
  manifest.json
  module.py
```

## 1. manifest.json

```json
{
  "id": "hello",
  "name": "Hello",
  "version": "1.0.0",
  "accent": "#7CFFB2",
  "interval": 5.0,
  "default_enabled": true,
  "settings": {
    "greeting": { "type": "string", "label": "Greeting", "default": "Hello" }
  }
}
```

* `id` — lowercase, stable, unique. Used in the protocol.
* `interval` — seconds between `update()` calls.
* `settings` — the dashboard auto-generates a form from this. Types:
  `string`, `number`, `boolean`, `enum` (with `options`), `shortcuts`.

## 2. module.py

```python
from core.base import Module

class Module(Module):
    async def update(self):
        self.value = "whatever you fetched"

    async def on_action(self, action: str, payload: dict):
        pass  # a control on the phone was pressed

    def page(self):
        return {
            "blocks": [
                {"type": "hero", "label": "MY DATA", "value": self.value, "unit": ""},
            ]
        }
```

## 3. Install it

Three ways, all without editing the server:

1. Copy the folder into `server/plugins/` and press **Rescan** in the dashboard.
2. Zip the folder and upload it in the dashboard's **Modules → Install** box.
3. Dashboard → **Download starter module**, edit, then install as above.

## Block reference

| type | fields |
|---|---|
| `hero` | `label, value, unit, sub, progress, icon, accent, slider` — add `slider: {action, value, min, max}` to put an interactive control inside the big number card |
| `gauges` | `items: [{label, value, suffix}]` |
| `sparkline` | `label, points[], min, max` |
| `meters` | `items: [{label, value, left, right}]` |
| `kv` | `items: [{label, value}]` |
| `list` | `title, items: [{title, sub, value, icon}]` |
| `controls` | `style: transport\|pill, items: [{id, icon, label, primary}]` |
| `slider` | `label, value, min, max, action` |
| `shortcuts` | `title, columns, items: [{id, label, icon, path}]` |
| `news` | `title, items: [{title, source, ago, url, image, action}]` — card per story, tap runs the action |

Button icons: `prev`, `next`, `play_pause`, `volume_up`, `volume_down`, `mute`.

## Notes

* `update()` runs every `interval` seconds — do slow network work in
  `asyncio.to_thread`.
* Call `self.push()` after handling an action for instant feedback.
* Set `refreshable = True` on your Module class to enable pull-to-refresh on the
  phone; the app then sends `{"action": "refresh"}` when the page is pulled down.
* A plugin that raises is logged and skipped; it can't take the server down.
* `self.settings` holds the values from the dashboard form.

## Dependencies

The packaged Windows build ships Python's standard library plus `psutil`,
`requests`, `pycaw` and `fastapi`. Plugins that import anything else will load
fine when you run the server from source (`python -m server.main`) but not in
the EXE. Keep third-party imports to that set, or add the package to
`packaging/build_exe.py`'s `--hidden-import` list and rebuild.
