# Build your own DeskGadget module

A module is just a folder with two files. You do not need to rebuild the
Android app: the phone renders whatever JSON your `page()` returns.

```
server/plugins/hello/
  manifest.json    what the dashboard shows and which settings exist
  module.py        your Python code
```

If you can write a small Python function, you can add a page to the deck.

---

## 1. The five-minute version

Copy the folder `server/plugins/timer` to `server/plugins/hello`, rename it,
then replace the two files with this:

**manifest.json**

```json
{
  "id": "hello",
  "name": "Hello",
  "version": "1.0.0",
  "author": "Your name",
  "description": "A tiny example module.",
  "accent": "#7CFFB2",
  "interval": 10.0,
  "default_enabled": true
}
```

**module.py**

```python
from core.base import Module as BaseModule


class Module(BaseModule):
    def page(self) -> dict:
        return {
            "blocks": [
                {
                    "type": "hero",
                    "label": "HELLO",
                    "value": "World",
                    "sub": "This page came from a module.",
                }
            ]
        }
```

Press **Rescan plugins** in the dashboard, then tick **Hello** for your phone.
That is a working module.

---

## 2. What goes in manifest.json

| Field | Required | What it does |
|---|---|---|
| `id` | yes | Lowercase, unique, no spaces. Used by the server and the app. |
| `name` | yes | The title in the dashboard and the tab on the phone. |
| `version` | yes | Shown in the dashboard. Bump it when you change your module. |
| `author` | no | Shown under the name. |
| `description` | no | One sentence explaining the module. |
| `accent` | no | A hex colour such as `#FFB86B`. Tints the phone's chrome for this module. |
| `interval` | no | Seconds between calls to `update()`. Use `0` or leave it out for never. |
| `default_enabled` | no | `true` means new installs can use it. Defaults to `true`. |
| `settings` | no | Form fields shown in the dashboard. See below. |

### Settings

The dashboard builds the form for you. Available types:

| Type | Example |
|---|---|
| `string` | `{"type":"string","label":"City","default":"London"}` |
| `number` | `{"type":"number","label":"Count","default":5}` |
| `boolean` | `{"type":"boolean","label":"Show icons","default":true}` |
| `enum` | `{"type":"enum","label":"Units","options":["C","F"],"default":"C"}` |
| `multienum` | `{"type":"multienum","label":"Topics","options":["Tech","Sport"],"default":["Tech"]}` |
| `shortcuts` | `{"type":"shortcuts","label":"Apps"}` — a built-in shortcut picker |

Read them in your code with `self.settings.get("city", "London")`. They are
plain values, already validated by the dashboard.

---

## 3. What goes in module.py

```python
from core.base import Module as BaseModule


class Module(BaseModule):
    async def update(self) -> None:
        # Called every `interval` seconds. Fetch data, update attributes.
        ...

    def page(self) -> dict:
        # Called when the phone needs a fresh page. Return {"blocks": [...]}.
        return {"blocks": []}

    async def on_action(self, action: str, payload: dict) -> None:
        # A button or tap on the phone. `action` is the id you put in the block;
        # `payload` may contain url, id, text or value.
        if action == "refresh":
            await self.update()
            self.push()          # tells the phone to re-render
```

Useful helpers on `BaseModule`:

| Helper | What it does |
|---|---|
| `self.push()` | Re-render this module's page on every phone that shows it. |
| `await self.hub.notify("Done")` | A short toast on the phone. |
| `self.accent` | The accent colour from your manifest. |
| `self.settings` | Current dashboard settings. |
| `self.errors` | Set to a short string to show an error on the page. |

Long work belongs in `update()` or in `asyncio.to_thread(...)`. Never block the
event loop with a slow network call.

---

## 4. Blocks: the page vocabulary

A page is a list of blocks. The phone decides the best layout: in landscape it
balances blocks into two or three columns automatically.

### hero

One big number or word. `unit`, `sub`, `icon`, `progress` and `slider` are
optional.

```json
{"type": "hero", "label": "CPU", "value": "42", "unit": "%",
 "sub": "8 cores", "progress": 0.42}
```

### kv

Small label/value pairs in one row. Keep values short.

```json
{"type": "kv", "items": [
  {"label": "Uptime", "value": "3d 4h"},
  {"label": "Battery", "value": "82%"}
]}
```

### list

Rows with an optional icon/image and an optional action. Tapping a row sends
`{"action": "open", "payload": {"url": "...", "id": "..."}}`.

```json
{"type": "list", "title": "RECENT FILES", "items": [
  {"title": "notes.txt", "sub": "2 KB", "value": "OPEN", "action": "open", "id": "notes.txt"}
]}
```

### controls

Buttons. `style` is `pill`, `grid`, `stack` or `transport`.

```json
{"type": "controls", "style": "pill", "items": [
  {"id": "start", "icon": "play_pause", "label": "Start"},
  {"id": "stop",  "icon": "pause",      "label": "Stop"}
]}
```

Built-in icon names: `prev`, `next`, `play_pause`, `pause`, `volume_up`,
`volume_down`, `mute`, `lock`, `screen_off`, `desktop`, `grid`, `camera`.
Anything else shows a neutral dot.

### gauges and meters

```json
{"type": "gauges", "items": [{"label": "CPU", "value": 62, "suffix": "%"}]}
{"type": "meters", "items": [
  {"label": "Disk C:", "value": 27, "left": "688 GB free", "right": "953 GB"}
]}
```

### note

A readable block of text, for clipboards or long status messages.

```json
{"type": "note", "label": "ON THE PC CLIPBOARD", "text": "Hello", "meta": "5 chars"}
```

### hours

A horizontal strip of small values, good for forecasts.

```json
{"type": "hours", "items": [
  {"label": "Now", "icon": "sun", "value": "21°"},
  {"label": "14:00", "icon": "cloud", "value": "20°"}
]}
```

### textinput

A text field plus a send button. The action receives `payload.text`.

```json
{"type": "textinput", "label": "SEND TO PC", "placeholder": "Type here",
 "button": "Send", "action": "send_text"}
```

### slider, toggles, nowplaying, news, shortcuts

These are used by the bundled modules; copy their `page()` output as a starting
point. You do not need them for a first module.

---

## 5. Making it fit a landscape phone

- Two blocks read better than five stacked ones. The app balances them for you.
- Force a column with `"col": 0`, `1` or `2` when order matters.
- Keep values short. Long text is truncated with an ellipsis.
- Font sizes are fixed for you, so prefer more blocks over huge paragraphs.
- Test on the phone in landscape. A page should be readable without scrolling;
  scrolling is allowed, but not required.

---

## 6. Actions and testing

1. Put `"action": "do_thing"` on a list row or an `id` on a control.
2. Read it in `on_action`.
3. Call `self.push()` when the page should change.

To test quickly:

- **Rescan plugins** in the dashboard reloads every folder in `plugins/`
  without restarting the server.
- The dashboard can be opened at `http://127.0.0.1:8787/`.
- Server logs show your module's errors. `log = logging.getLogger("deskgadget.mymodule")`.
- If the page does not change, check that `page()` returns `{"blocks": [...]}`
  with at least one block.

Wrap network calls in `try/except` and put the problem in a hero `sub`, so a
failed fetch never leaves a blank page:

```python
try:
    data = await fetch()
    self.error = ""
except Exception as exc:
    self.error = f"Could not fetch: {exc}"
```

---

## 7. Installing and sharing

- **Local:** copy the folder into `server/plugins/`, press **Rescan plugins**.
- **Zip:** zip the module folder (so the zip contains `manifest.json` at the
  top level) and drop it on the dashboard.
- **Catalogue:** the **Add or remove modules** button lists modules that ship
  with DeskGadget and installs them from GitHub.

A module is portable: it is only Python plus JSON. There is no app rebuild,
no signing, and no store review.

---

## 8. Common mistakes

| Symptom | Cause |
|---|---|
| Module not listed | `manifest.json` is not valid JSON, or `id` is missing. |
| Phone shows nothing | `page()` returned no blocks, or the module is disabled for that phone. |
| Settings ignored | You read `self.settings` directly without a `.get()` default on first run. |
| Action does nothing | The id in the block and the `if action == ...` string do not match. |
| Page is stale | Call `self.push()` after changing state or handling an action. |
| Server feels slow | A blocking call inside `page()` or `on_action()`. Move it to `update()` or `to_thread`. |

---

## 9. Copy-paste starter

The dashboard's **Download starter module** button gives you a ready folder with
a manifest, a working page and a button. Edit those three things and you have a
module:

1. `page()` — what the phone shows.
2. `on_action()` — what a tap does.
3. `manifest.json` — the name, colour and settings.

That is the whole contract.
