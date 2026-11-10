# DeskGadget MAC

Standalone macOS server for DeskGadget. It speaks the same protocol as the
Windows build, so **the same Android APK** is the endpoint — no app changes.

* Native dashboard window (`WKWebView`), no browser
* Menu bar **DG**: Open DeskGadget · Reload · Data Folder · Login Items · Quit
* CoreAudio volume and per-device mute, Accessibility window switcher, Quartz
  touchpad, `pbpaste` clipboard, `screencapture`
* Self-contained `.app` and DMG: Python 3.12, dependencies, plugins, dashboard
  and `adb` are bundled

## Install

Download **`DeskGadget-MAC-<version>-arm64.dmg`** from
[Releases](https://github.com/issacjohn/deskgadget/releases), drag
**DeskGadget** into Applications, and open it.

Apple Silicon, macOS 11+. The build is ad-hoc signed: right-click → **Open** the
first time if Gatekeeper complains. On first launch the app asks macOS for the
permissions it needs (Accessibility, Screen Recording, Automation); grant them
in the dashboard's **MAC SETUP** card.

## Run from source

```bash
./install.command      # creates .venv, seeds Application Support, starts it
./run.command          # foreground/development
```

## Build the app + DMG

```bash
./packaging/build_mac_bundle.sh
# dist/DeskGadget.app
# dist/DeskGadget-<version>-arm64.dmg
```

Uses a portable CPython 3.12 (macOS 11+) downloaded into `.build/`; no Homebrew
Python needed. For distribution, pass your signing identity:

```bash
CODESIGN_IDENTITY="Developer ID Application: …" \
NOTARY_PROFILE=deskgadget-notary \
./packaging/build_mac_bundle.sh
```

## Docs

Full setup, permissions, transports, camera/OBS route, VPN caveat and
troubleshooting: **[MAC.md](MAC.md)**.
