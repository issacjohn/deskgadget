#!/bin/bash
# DeskGadget for macOS — one-time installer.
#
# Creates a private Python environment in this folder, installs the server
# dependencies, seeds your data folder, and registers a LaunchAgent so the
# server starts at login. Nothing is installed into /Applications and no
# administrator password is needed.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DATA="${DESKGADGET_DATA:-$HOME/Library/Application Support/DeskGadget}"
PORT="${DESKGADGET_PORT:-8787}"
LABEL="com.deskgadget.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/DeskGadget.log"

say() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }

say "DeskGadget — macOS setup"
echo "  folder : $ROOT"
echo "  data   : $DATA"
echo

# ---- 1. find a usable Python (3.9+, newest first) --------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$(command -v "$candidate")"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  warn "No Python 3.9+ found."
  echo "Install it once with:  brew install python@3.12"
  echo "or download it from https://www.python.org/downloads/macos/"
  echo
  echo "Press return to close."
  read -r _ || true
  exit 1
fi
echo "Using Python: $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"

# ---- 2. virtual environment ------------------------------------------------
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  "$PY" -m venv "$ROOT/.venv" || {
    warn "Could not create .venv. On very old systems install Xcode command line tools: xcode-select --install"
    exit 1
  }
fi

"$ROOT/.venv/bin/python" -m pip install --quiet --upgrade pip setuptools wheel

say "Installing server dependencies…"
if ! "$ROOT/.venv/bin/pip" install --quiet -r "$ROOT/server/requirements-mac.txt"; then
  warn "Some optional packages (pyobjc) have no wheel for this Python/macOS."
  warn "Installing the core dependencies only — the server will use AppleScript fallbacks."
  "$ROOT/.venv/bin/pip" install --quiet fastapi 'uvicorn[standard]' websockets psutil zeroconf requests pillow || exit 1
fi

# ---- 3. seed the user data folder -----------------------------------------
# State lives outside the checkout so a re-install never loses devices,
# themes, module settings or modules you removed on purpose.
mkdir -p "$DATA/plugins" "$DATA/data" "$HOME/Library/Logs"

# dashboard + starter module are assets, not user state: refresh them
rm -rf "$DATA/dashboard"
cp -R "$ROOT/server/dashboard" "$DATA/dashboard"
rm -rf "$DATA/templates"
cp -R "$ROOT/server/templates" "$DATA/templates"

# bundled modules are only added if neither installed nor removed by the user
for src in "$ROOT/server/plugins"/*; do
  [ -d "$src" ] || continue
  name="$(basename "$src")"
  case "$name" in
    __pycache__|.*) continue ;;
  esac
  if [ -d "$DATA/plugins/$name" ] || [ -d "$DATA/plugins_removed/$name" ]; then
    continue
  fi
  cp -R "$src" "$DATA/plugins/$name"
  echo "  added module: $name"
done

# ---- 4. start automatically -------------------------------------------------
# Preferred: a LaunchAgent. Some Macs have ~/Library/LaunchAgents owned by root,
# so fall back to a Login Item pointing at a real .app bundle (no admin rights,
# and TCC then attributes permissions to "DeskGadget" rather than python).
USE_AGENT=0
mkdir -p "$HOME/Library/LaunchAgents" 2>/dev/null || true
if [ -w "$HOME/Library/LaunchAgents" ]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/.venv/bin/python</string>
    <string>-m</string>
    <string>server.main</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DESKGADGET_ROOT</key><string>$ROOT/server</string>
    <key>DESKGADGET_DATA</key><string>$DATA</string>
    <key>DESKGADGET_PORT</key><string>$PORT</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLISTEOF
  then
    launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || launchctl unload "$PLIST" >/dev/null 2>&1 || true
    if launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || launchctl load "$PLIST" >/dev/null 2>&1; then
      USE_AGENT=1
      echo "  login agent installed"
    fi
  fi
fi

if [ "$USE_AGENT" -ne 1 ]; then
  warn "This Mac's ~/Library/LaunchAgents is not writable — using a Login Item instead."
  APP_SRC="$ROOT/dist/DeskGadget.app"
  if [ ! -d "$APP_SRC" ]; then
    "$ROOT/packaging/build_mac_bundle.sh" >/dev/null 2>&1 || true
  fi
  if [ -d "$APP_SRC" ]; then
    DEST="/Applications/DeskGadget.app"
    if ! mkdir -p /Applications 2>/dev/null || [ ! -w /Applications ]; then
      mkdir -p "$HOME/Applications"
      DEST="$HOME/Applications/DeskGadget.app"
    fi
    rm -rf "$DEST"
    cp -R "$APP_SRC" "$DEST"
    APP_INSTALLED="$DEST"
    echo "  installed $DEST"
    echo "  open it from the Dock; add Login Items if you want it at login"
  else
    warn "Could not build the standalone app; start it with mac/run.command."
  fi
fi

# ---- 5. start now and wait for the dashboard -------------------------------
say "Starting the server…"
if [ "$USE_AGENT" -ne 1 ]; then
  # start it for this session too, so the phone works immediately
  env DESKGADGET_ROOT="$ROOT/server" DESKGADGET_DATA="$DATA" DESKGADGET_PORT="$PORT" \
      PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
      nohup "$ROOT/.venv/bin/python" -m server.main >>"$LOG" 2>&1 &
fi

for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if curl -fsS "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
  say "DeskGadget is running at http://localhost:$PORT"
  open "http://localhost:$PORT" >/dev/null 2>&1 || true
else
  warn "The server did not answer yet. See $LOG"
fi

if [ "$USE_AGENT" -eq 1 ]; then
  PERM_TARGET="$ROOT/.venv/bin/python"
  START_NOTE="Starts automatically at login (LaunchAgent)."
else
  PERM_TARGET="${APP_INSTALLED:-$HOME/Applications/DeskGadget.app}"
  START_NOTE="Open DeskGadget from the Dock; add it to Login Items to start with the Mac."
fi

cat <<DONE

── Permissions (only the modules you use need these) ──────────────────────
Accessibility      window switcher, touchpad, lock / desktop keys
Screen Recording   screenshots
Automation         media control and hiding apps

Open the dashboard → MAC SETUP card, click Open next to a row, and add:
  $PERM_TARGET
On macOS 13+ use ⌘⇧G in the file picker to paste that path.
On older systems the same panes live in System Preferences → Security & Privacy.
───────────────────────────────────────────────────────────────────────────
$START_NOTE
Phone: install DeskGadget.apk from github.com/issacjohn/deskgadget/releases
       and keep the phone on the same Wi-Fi, or enable USB tethering.
DONE

echo
echo "Press return to close."
read -r _ || true
