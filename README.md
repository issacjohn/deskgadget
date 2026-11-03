<div align="center">

<img src="docs/screenshots/icon.png" width="96" alt="DESKGadget" />

# DESKGadget

**A liquid-glass control panel for your Windows PC — one page per module, on a phone you already own.**

Windows server · Android client · plugins anyone can write

</div>

> **Built to be better than DeskThing.** DeskThing proved the idea: a small screen
> on your desk showing your PC. DESKGadget takes the same idea and removes the
> two things that hold it back — you never rebuild the app to add a module, and
> you choose exactly which modules each device sees. Everything is declarative
> data over one WebSocket, so a new plugin is a folder on the PC.

---

## Screenshots

| System | Media |
|---|---|
| ![System](docs/screenshots/system.jpg) | ![Media](docs/screenshots/media.jpg) |

| News | Shortcuts |
|---|---|
| ![News](docs/screenshots/news.jpg) | ![Shortcuts](docs/screenshots/shortcuts.jpg) |

| OLED Black | White |
|---|---|
| ![OLED](docs/screenshots/theme-black.jpg) | ![White](docs/screenshots/theme-white.jpg) |

![Dashboard](docs/screenshots/dashboard.jpg)

---

## Why another one?

| | DeskThing | DESKGadget |
|---|---|---|
| Adding a module | ships code for the client | **declarative blocks, no app rebuild** |
| Module choice | one layout for all devices | **per-device tick list + drag order** |
| Plugin authoring | TypeScript project | **a folder with `manifest.json` + `module.py`** |
| Plugin install | rebuild / restart | **drop a zip on the dashboard, hot reload** |
| Themes | dark | **six, including true OLED black and a light one** |
| Media | volume + transport | **+ per-output and per-microphone mute** |
| Games | manual shortcuts | **Steam libraries scanned automatically, cover art fetched** |
| Transport | polling in places | **push-only WebSocket for both phone and dashboard** |
| Output | — | **one installer, one APK, no Python required** |

## Modules

| Module | What it does |
|---|---|
| **System** | CPU, RAM, disk, network, uptime, top processes, live sparkline |
| **Media** | PC volume + slider, transport, mute **each output**, mute **each microphone** |
| **News** | Multi-region, multi-topic headlines with publisher logos; tap opens on the PC |
| **Shortcuts** | Launch Windows apps; **Steam games detected automatically** with cover art |
| **Weather** | Current + hourly + 7-day, no API key |
| **Drives** | Ring per volume, free/total meters |
| **Network** | Public/LAN IP, latency, live throughput |
| **Quick** | Lock, screen off, show desktop, screenshot |
| **Timer** | Countdown / Pomodoro with start, +5, reset |
| **AudioMesh** | Example third-party module (ship your own the same way) |

Each is its own swipeable page. Tick only what a given phone should show.

## Architecture

```
server/                 Python 3.11+ — FastAPI + WebSocket
  core/                 protocol, hub, plugin loader, adb bridge, launcher
  plugins/<id>/         manifest.json + module.py
  dashboard/            the glass dashboard served at :8787
android/                Kotlin + Jetpack Compose, minSdk 26
packaging/              launcher, installer, PyInstaller build, icon extractor
docs/screenshots/       the images above
```

**Transport is push-only.** The phone holds one WebSocket; the server samples each
module on its interval and sends a rendered page only when it changed. Controls
travel back on the same socket and the module pushes again immediately. The
dashboard has its own socket (`/ws/dashboard`); nothing polls in a loop.

**The phone is a renderer.** Modules emit a tree of blocks — `hero`, `gauges`,
`sparkline`, `meters`, `kv`, `list`, `controls`, `slider`, `shortcuts`, `news`,
`toggles` — and the app draws them. Adding a module therefore never requires an
app update, which is the whole point.

## Install

**Windows** — run `DESKGadget-Setup.exe` from [Releases](../../releases). It installs
to `%LOCALAPPDATA%\DESKGadget`, adds Desktop and Start Menu shortcuts, and starts
the dashboard. No admin rights, **no Python required** (the interpreter and `adb`
are bundled).

**Android** — install `DESKGadget.apk` from Releases. It finds the server over
mDNS, over the UDP beacon, or over USB (`adb reverse` is kept alive by the server),
and reconnects to whichever route is up.

```bash
# from source
pip install -r server/requirements.txt
python -m server.main        # dashboard at http://localhost:8787
```

## Writing a module

```python
# server/plugins/hello/module.py
from core.base import Module

class Module(Module):
    def page(self):
        return {"blocks": [
            {"type": "hero", "label": "HELLO", "value": "42", "unit": "%"}
        ]}
```

```json
// server/plugins/hello/manifest.json
{ "id": "hello", "name": "Hello", "accent": "#7CFFB2",
  "interval": 5, "settings": { "greeting": { "type": "string", "default": "hi" } } }
```

Then **Rescan** in the dashboard, or zip the folder and drop it in. See
[`server/PLUGINS.md`](server/PLUGINS.md) for every block and setting type.

## Themes

Liquid · Full Glass · OLED Black · White · Graphite · Aurora — picked per device
in the dashboard, applied live, remembered across reconnects.

## Build

```bash
# android (JDK 17 or 21, SDK 35)
cd android && gradle assembleDebug

# windows installer (Python 3.11+, PyInstaller)
powershell packaging/fetch_adb.ps1
python packaging/build_exe.py     # dist/DESKGadget-Setup.exe
```

## Roadmap

- Now Playing (track, artwork, seek) — needs `winsdk` bundled
- Window switcher (focus/minimise any window)
- Wake-on-LAN for other machines
- Clipboard bridge
- Home Assistant, GitHub notifications, Steam deals

## License

MIT — see [LICENSE](LICENSE).
