# DeskGadget on macOS

The same DeskGadget server, running on a Mac instead of a Windows PC, with the
**unchanged Android app** as the endpoint. One WebSocket, the same block
protocol, the same per-device layout, themes and module folders.

Tested end-to-end on macOS 27.2 (Apple Silicon) with a Samsung SM-G980F over
Wi-Fi, with the USB/adb reverse route bridged alongside it. The code is written
to work on **every macOS from 10.15 Catalina onward**, Intel or Apple Silicon,
Python 3.9–3.14.

---

## Install the app (recommended)

A built **`dist/DeskGadget-<version>-arm64.dmg`** is included. Open it, drag
**DeskGadget** into *Applications*, and launch it.

The bundle is self-contained: Python 3.12, every dependency, the server, the
dashboard, all bundled modules and `adb` are inside the `.app`. Nothing else to
install — no Homebrew, no Python, no developer tools, and **no browser**.

* The dashboard opens in the app's **own native window** (`WKWebView`), with a
  Dock icon, App menu (`⌘Q`) and Edit menu (copy/paste inside the dashboard).
* Closing the window does **not** stop the server: click the Dock icon, the
  **DG** menu bar item, or *Open DeskGadget* to bring it back.
* First launch seeds `~/Library/Application Support/DeskGadget`, starts the
  server and shows the window.
* Menu bar: **Open DeskGadget · Reload Dashboard · Open Data Folder · Login
  Items… · Quit**.
* It starts when you open it — no background item is installed. To start it
  with the Mac, add it in System Settings → General → **Login Items** (or the
  menu bar's *Login Items…*). At login it shows its window; close it to leave
  the server in the menu bar.
* The build is ad-hoc signed. If Gatekeeper warns, right-click → **Open** once.

The bundled runtime targets **macOS 11+ on Apple Silicon** (every Apple Silicon
Mac). PyInstaller cannot merge an Intel and an ARM build into one universal
binary from an ARM machine; Intel Macs use the source install below, which
pip-installs native wheels.

## From source (development, Intel, or custom Python)

1. Double-click **`mac/install.command`**.
   It creates `.venv`, installs the dependencies, seeds
   `~/Library/Application Support/DeskGadget`, and — where
   `~/Library/LaunchAgents` is writable — registers a LaunchAgent. Otherwise it
   installs the standalone app for you to open, and leaves auto-start to you.
2. The dashboard opens at <http://localhost:8787>.
3. Install `DeskGadget.apk` from the
   [releases page](https://github.com/issacjohn/deskgadget/releases) on the
   phone. It is the same APK — nothing Android-side changed.
4. Open the app, pick this Mac from the list, done.

Foreground/development run: **`mac/run.command`** (data stays in `server/data`).

## Build the app yourself

```bash
./packaging/build_mac_bundle.sh
# dist/DeskGadget.app
# dist/DeskGadget-<version>-arm64.dmg
```

The script downloads a portable CPython 3.12 (macOS 11+) into `.build/`, builds
with PyInstaller, bundles adb, writes the menu-bar `Info.plist`, ad-hoc signs,
and produces the DMG. For distribution with your own certificate:

```bash
CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
NOTARY_PROFILE=deskgadget-notary \
./packaging/build_mac_bundle.sh
```

`NOTARY_PROFILE` is a `xcrun notarytool store-credentials` profile; when set,
the DMG is notarized and stapled.

For a stable *local* signature (so TCC grants survive rebuilds):

```bash
./packaging/create_signing_identity.sh
CODESIGN_IDENTITY="DeskGadget Local" ./packaging/build_mac_bundle.sh
```

---

## Requirements

| | |
|---|---|
| macOS | 10.15 Catalina → current (26/27); bundled app 11+ (Apple Silicon) |
| CPU | Intel x86_64 or Apple Silicon arm64 |
| Python | app: bundled. Source: 3.9+ (3.12/3.13 recommended) |
| Optional | `adb` for USB mode, `nowplaying-cli` for browser media, OBS for virtual camera |

The only mandatory tools are the ones macOS ships with: `osascript`,
`pbpaste`/`pbcopy`, `screencapture`, `pmset`, `open`, `sips`, `sysctl`.
**pyobjc is optional** — the server detects it at runtime and falls back to
AppleScript or CLI tools when it is missing.

---

## Connecting the phone

Three transports, exactly like the Windows build:

| Mode | How | Notes |
|---|---|---|
| **Wi-Fi** | same network, discovered by mDNS + UDP beacon | zero setup |
| **USB tethering** | enable *USB tethering* on the phone | no adb, no developer options |
| **USB + adb** | enable USB debugging, accept the prompt | server keeps `adb reverse tcp:8787 tcp:8787` alive; phone uses `127.0.0.1` |

`adb` is looked up on `PATH` and in the usual Homebrew/Android SDK locations:

```
/opt/homebrew/bin/adb
/usr/local/bin/adb
~/Library/Android/sdk/platform-tools/adb
/opt/homebrew/share/android-commandlinetools/platform-tools/adb
```

Install it with `brew install --cask android-platform-tools` or
`brew install android-commandlinetools`.

The mDNS name is suffixed with the Mac's hostname
(`DeskGadget (ISSJOHN-M-T20Q)`) so a LAN with several decks does not show three
identical entries.

### VPN caveat (important)

A VPN that claims the whole LAN subnet overrides the Wi-Fi route. You can see it
with:

```bash
netstat -rn -f inet | grep '^192.168'
# 192.168.0  link#25  UCS  utun5      ← VPN owns the LAN, mDNS cannot cross
```

Symptoms: the phone cannot ping the Mac and never sees it in the connect list,
while other PCs on the LAN still appear. Disconnect the VPN, or use USB
(`127.0.0.1` through `adb reverse`), which is unaffected.

---

## Permissions (per app, granted once)

macOS has no global "allow this program" switch; TCC attributes every permission
to the binary that asks.

| Permission | Used by | Needed for |
|---|---|---|
| **Accessibility** | `core/mac/windows.py`, `core/mac/pointer.py` | window switcher, touchpad, lock/desktop keystrokes |
| **Screen Recording** | `core/mac/power.py` | screenshots |
| **Automation** | `core/mac/media.py`, `power.py` | Music/Spotify control, hiding apps, volume fallback |
| **Local Network** (15+) | `core/netutil.py` | mDNS discovery, UDP beacon |
| **Microphone / Camera** | the phone, not the Mac | camera module |

The dashboard has a **MAC SETUP** card that reports the state and deep-links to
the right System Settings pane. The bundled app also asks macOS for the three
permissions **automatically on first launch** (Accessibility, Screen
Recording, Automation) — the real system dialogs, not a web page. If a switch is
still off afterwards, the card's **Enable** button triggers the prompt again;
macOS never lets an app grant itself, so the final step is flipping DeskGadget
in the pane that opens. Prompts are attempted once per build, then the card is
the way back in.

**Why it may still not appear in the list.** Accessibility is owned by TCC, not
by the app. macOS remembers the app by its *code identity*: an ad-hoc build gets
a new hash every time, so after a rebuild an existing grant no longer applies
and the app can look "new" to the list. Two fixes:

* **Stable local identity** (recommended for your own Mac):
  `./packaging/create_signing_identity.sh`, then
  `CODESIGN_IDENTITY="DeskGadget Local" ./packaging/build_mac_bundle.sh`.
  Grants then survive rebuilds.
* **Distribution**: a Developer ID certificate + notarization (see Build).

If it is already missing, the MAC SETUP card's *Show DeskGadget in Finder*
reveals the app; drag it into the Accessibility list — that always works.

Which binary to add depends on how you started the server:

* `mac/install.command` → LaunchAgent runs `.venv/bin/python`
  → add `<this folder>/.venv/bin/python` under Accessibility.
* The standalone app → add **DeskGadget** (`/Applications/DeskGadget.app`);
  macOS also shows it automatically once it asks for a permission.

In the file picker use **⌘⇧G** to paste the path. After granting Accessibility,
restart the server (or toggle the app off/on in the list).

---

## What each module does on macOS

| Module | Backend | Fallback |
|---|---|---|
| **System** | psutil + `sysctl` + `pmset` + `screencapture` | — |
| **Media** | CoreAudio (ctypes) for volume and per-device mute; AppleScript or `nowplaying-cli` for transport | `osascript set volume` |
| **Windows** | Accessibility API (`AXUIElement`) + NSWorkspace | CoreGraphics (`CGWindowList`) + app activation; no permission needed |

The window switcher is the one module with a no-permission path: without
Accessibility it lists every visible window through CoreGraphics and tapping a
row activates that app. Accessibility adds per-window focus, and Screen
Recording fills in the window titles. macOS never requires either permission
just to switch apps.
| **Touchpad** | Quartz `CGEvent` | `cliclick` |
| **Clipboard** | `pbpaste` / `pbcopy` | — |
| **Shortcuts** | `/Applications` scan, `open`, `.icns` → PNG via `sips` | NSWorkspace icon |
| **Drives** | psutil (APFS-aware), skips `/System/Volumes/*` | — |
| **Weather / News / Timer / WOL** | network only | — |
| **Camera** | MJPEG stream + OBS Virtual Camera | see below |
| **AudioMesh** | disabled by default; it is the Windows third-party example | — |

Native helpers live in **`server/core/mac/`**:
`audio.py`, `media.py`, `windows.py`, `pointer.py`, `power.py`, `clipboard.py`.

### Camera / virtual webcam

There is no DirectShow on macOS, so the Windows UnityCapture filter is replaced
by **OBS's CoreMediaIO plugin**:

* **Zero-dependency route** — in OBS add a *Media Source* with
  `http://<this-mac>:8787/api/camera/stream`, then *Start Virtual Camera*.
  Every conferencing app sees "OBS Virtual Camera".
* **Direct feed** — install OBS and `pyvirtualcam`:
  `.venv/bin/pip install pyvirtualcam`. DeskGadget then pushes frames straight
  into OBS's device (one phone at a time; macOS exposes a single OBS camera,
  unlike the per-phone slots on Windows).

The camera module still receives frames and exposes `/api/camera/latest.jpg`
and `/api/camera/stream` on every Mac, with no OBS installed.

---

## Updating

There is no GitHub updater on the macOS build (the public release feed carries
the Windows installer).

* **Bundled app** — quit it from the menu bar, drag the new
  `DeskGadget.app` over the old one in Applications, reopen. Device pairings,
  themes and settings in Application Support are preserved.
* **Source** — pull the folder, then `mac/install.command`. That never
  overwrites `~/Library/Application Support/DeskGadget/data` (devices, themes,
  settings) and never re-adds a module you removed; it only copies modules that
  are neither installed nor in `plugins_removed/`.

## Start, stop, restart

The app is a normal Dock application with a native dashboard window. Closing
the window leaves the server running in the menu bar.

```bash
open -n /Applications/DeskGadget.app  # open the window
pkill -f "server.main"                # stop a source install
mac/run.command                       # start in the foreground (dev)
```

Logs: `~/Library/Logs/DeskGadget.log` (source installer) and
`~/Library/Application Support/DeskGadget/data/server.log` (both).

## Uninstalling

`mac/uninstall.command` removes the login item and offers to delete data,
`.venv` and the installed `.app`.

---

## Troubleshooting

**Dashboard does not open.** Check the log:
`~/Library/Logs/DeskGadget.log` (installer) or the terminal (run.command).

**Phone list is empty.** Same Wi-Fi? VPN off? Then check Local Network
permission and the macOS firewall (allow incoming connections for Python or
DeskGadget). USB mode always works as a cross-check.

**"Reconnecting…" forever.** The app remembers each transport separately. Open
the heart → *Disconnect* → pick this Mac. USB and Wi-Fi keep separate addresses.

**Windows module shows 0.** Accessibility is not granted, or the process was
restarted after the grant. The MAC SETUP card shows the exact state.

**Media controls do nothing.** Music/Spotify need Automation permission. For
browser playback install `nowplaying-cli` (`brew install nowplaying-cli`), which
reads the system now-playing centre for any app.

**Touchpad does nothing.** Needs pyobjc (Quartz) or `cliclick`, plus
Accessibility.

**`adb: no devices`.** Accept the "Allow USB debugging" prompt on the phone.
`adb devices` should say `device`, not `unauthorized`.

**pyobjc failed to install.** Harmless: the installer continues with the core
dependencies and the AppleScript fallbacks. Retry later with a newer Python
(`brew install python@3.13`).

---

## Folding this back into the upstream repo

The port is deliberately kept in additive files plus a small set of module
rewrites, so it can live on a branch:

* **new** `server/core/mac/`, `server/core/seed.py`,
  `server/requirements-mac.txt`, `mac/`,
  `packaging/build_mac_bundle.sh`, `packaging/mac_entry.py`, `MAC.md`
* **rewritten for macOS** `core/launcher.py`, `core/vcam.py`,
  `plugins/{system,media,windows,touchpad,clipboard,drives,shortcuts}`
* **guarded** `core/paths.py` (frozen vs source layout), `core/updates.py` (no
  Windows updater on macOS), `core/web.py` (no `ctypes.wintypes` import on
  non-Windows), `core/netutil.py` (adb lookup), `main.py` (platform field,
  `/api/mac/*`, virtual-camera backend, seed on launch)
* **unchanged** Android client, protocol, hub, store, plugin loader, dashboard
  shell, weather/news/timer/wol modules

To keep both platforms in one tree, move the OS calls behind
`core/platform/{base,win,mac}.py` and select at import time; the module
contracts (block shapes, action names) are already identical.
