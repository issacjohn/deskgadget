#!/bin/bash
# Build a self-contained DeskGadget.app and a drag-to-Applications DMG.
#
# The bundle includes the Python runtime, every dependency, the server, the
# dashboard, bundled plugins and adb — nothing needs to be installed first.
#
# Python: uses the portable CPython in .build/python (macOS 11+ on Apple
# Silicon, independent of Homebrew). If it is missing it is downloaded once.
#
# Optional environment:
#   CODESIGN_IDENTITY   "Developer ID Application: ..." for distribution
#                       (default "-" = ad-hoc, fine for personal use)
#   NOTARY_PROFILE      notarytool keychain profile; if set, the DMG is
#                       notarized and stapled after signing
#   DESKGADGET_TARGET_ARCH  universal2|x86_64|arm64 when the build Python
#                       supports it
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(cat VERSION 2>/dev/null || echo 1.0.0)"
BUILD_VERSION="$(printf '%s' "$VERSION" | tr -cd '0-9.')"
[ -n "$BUILD_VERSION" ] || BUILD_VERSION="1.0.0"
ARCH="$(uname -m)"
BUILD="$ROOT/.build"
APP="$ROOT/dist/DeskGadget.app"
PY="$BUILD/python/bin/python3"
VENV="$BUILD/venv"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.12.16%2B20261026-aarch64-apple-darwin-install_only.tar.gz"

say() { printf "\033[1m%s\033[0m\n" "$*"; }

mkdir -p "$ROOT/dist"

# ---- 1. portable Python ----------------------------------------------------
if [ ! -x "$PY" ]; then
  say "Fetching portable Python 3.12 (macOS 11+)…"
  mkdir -p "$BUILD"
  curl -fL --retry 3 -o "$BUILD/pbs.tar.gz" "$PBS_URL"
  tar -xzf "$BUILD/pbs.tar.gz" -C "$BUILD"
fi

# ---- 2. build environment --------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$ROOT/server/requirements-mac.txt"
"$VENV/bin/python" -c "import PyInstaller" 2>/dev/null || \
  "$VENV/bin/pip" install --quiet pyinstaller

# ---- 3. icon ---------------------------------------------------------------
ICNS="$BUILD/AppIcon.icns"
if [ ! -f "$ICNS" ] && [ -f "$ROOT/docs/screenshots/icon.png" ]; then
  TMP="$(mktemp -d)"
  ICONSET="$TMP/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
              "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
              "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
    size="${spec%% *}"
    name="${spec##* }"
    /usr/bin/sips -z "$size" "$size" "$ROOT/docs/screenshots/icon.png" \
      --out "$ICONSET/$name.png" >/dev/null 2>&1 || true
  done
  /usr/bin/iconutil -c icns "$ICONSET" -o "$ICNS" >/dev/null 2>&1 || true
  rm -rf "$TMP"
fi

# ---- 4. adb (universal binary) --------------------------------------------
ADB=""
for candidate in \
  "/opt/homebrew/share/android-commandlinetools/platform-tools/adb" \
  "/usr/local/share/android-commandlinetools/platform-tools/adb" \
  "$HOME/Library/Android/sdk/platform-tools/adb" \
  "/opt/homebrew/bin/adb" "/usr/local/bin/adb"; do
  if [ -x "$candidate" ]; then ADB="$candidate"; break; fi
done

# ---- 5. PyInstaller --------------------------------------------------------
say "Building DeskGadget.app (this takes a minute)…"
rm -rf "$APP" "$BUILD/pyinstaller" "$BUILD/DeskGadget.spec"

ARGS=(
  --noconfirm --clean --windowed
  --name DeskGadget
  --osx-bundle-identifier com.deskgadget.mac
  --distpath "$ROOT/dist"
  --workpath "$BUILD/pyinstaller"
  --specpath "$BUILD"
  --paths "$ROOT"
  --hidden-import server.main
  --hidden-import WebKit
  --collect-submodules server.core
  --add-data "$ROOT/server/plugins:plugins"
  --add-data "$ROOT/server/dashboard:dashboard"
  --add-data "$ROOT/server/templates:templates"
  --add-data "$ROOT/VERSION:."
  --exclude-module tkinter
  --exclude-module matplotlib
  --exclude-module numpy
)
[ -n "$ADB" ] && ARGS+=(--add-binary "$ADB:bin")
[ -f "$ICNS" ] && ARGS+=(--icon "$ICNS")

# Dynamic imports (the `core.*` alias used by plugins, and lazy OS backends)
# are invisible to the analyser; list every core module explicitly.
for file in "$ROOT"/server/core/*.py "$ROOT"/server/core/mac/*.py; do
  [ -f "$file" ] || continue
  base="$(basename "$file" .py)"
  [ "$base" = "__init__" ] && continue
  case "$file" in
    */core/mac/*) ARGS+=(--hidden-import "server.core.mac.$base") ;;
    *)            ARGS+=(--hidden-import "server.core.$base") ;;
  esac
done
if [ -n "${DESKGADGET_TARGET_ARCH:-}" ]; then
  ARGS+=(--target-arch "$DESKGADGET_TARGET_ARCH")
fi

"$VENV/bin/pyinstaller" "${ARGS[@]}" "$ROOT/packaging/mac_entry.py" \
  > "$BUILD/pyinstaller.log" 2>&1 || {
    tail -40 "$BUILD/pyinstaller.log"
    exit 1
  }

# ---- 5b. permission-free media helper (BSD-3) -----------------------------
VENDOR="$ROOT/vendor/mediaremote"
if [ -d "$VENDOR" ]; then
  DEST="$APP/Contents/Frameworks/mediaremote"
  rm -rf "$DEST"
  mkdir -p "$DEST"
  ditto "$VENDOR/MediaRemoteAdapter.framework" "$DEST/MediaRemoteAdapter.framework"
  cp "$VENDOR/mediaremote-adapter.pl" "$DEST/"
  cp "$VENDOR/LICENSE" "$DEST/" 2>/dev/null || true
  cp "$VENDOR/NOTICE" "$DEST/" 2>/dev/null || true
  chmod +x "$DEST/mediaremote-adapter.pl"
fi

# ---- 6. Info.plist ---------------------------------------------------------
PLIST="$APP/Contents/Info.plist"
pb() { /usr/libexec/PlistBuddy -c "$1" "$PLIST" >/dev/null 2>&1 || true; }

if [ "$ARCH" = "arm64" ]; then MIN_OS="11.0"; else MIN_OS="10.15"; fi
# A regular Dock application with a native window; the menu bar item is extra.
pb "Delete :LSUIElement"
pb "Add :LSUIElement bool false"
pb "Delete :LSMinimumSystemVersion"
pb "Add :LSMinimumSystemVersion string $MIN_OS"
pb "Delete :NSHighResolutionCapable"
pb "Add :NSHighResolutionCapable bool true"
pb "Delete :NSAppleEventsUsageDescription"
pb "Add :NSAppleEventsUsageDescription string DeskGadget controls media apps and hides windows when you tap a control on your phone."
pb "Delete :NSLocalNetworkUsageDescription"
pb "Add :NSLocalNetworkUsageDescription string DeskGadget advertises itself on your local network so your phone can find this Mac."
pb "Delete :NSHumanReadableCopyright"
pb "Add :NSHumanReadableCopyright string MIT — DeskGadget"
pb "Delete :LSApplicationCategoryType"
pb "Add :LSApplicationCategoryType string public.app-category.utilities"
pb "Set :CFBundleShortVersionString $VERSION"
pb "Set :CFBundleVersion $BUILD_VERSION"

# keep adb executable after PyInstaller's copy
find "$APP" -type f -name adb -exec chmod +x {} \; 2>/dev/null || true

# ---- 7. sign ---------------------------------------------------------------
IDENTITY="${CODESIGN_IDENTITY:--}"
if [ "$IDENTITY" = "-" ]; then
  /usr/bin/codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
  say "Signed ad-hoc (right-click → Open on first launch)"
else
  /usr/bin/codesign --force --deep --options runtime --timestamp \
    --sign "$IDENTITY" "$APP"
  say "Signed with $IDENTITY"
fi

# ---- 8. DMG ----------------------------------------------------------------
say "Making DMG…"
DMG="$ROOT/dist/DeskGadget-$VERSION-$ARCH.dmg"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
/usr/bin/hdiutil create -quiet -volname "DeskGadget" -srcfolder "$STAGE" \
  -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

if [ "$IDENTITY" != "-" ]; then
  /usr/bin/codesign --force --sign "$IDENTITY" "$DMG" >/dev/null 2>&1 || true
  if [ -n "${NOTARY_PROFILE:-}" ]; then
    say "Notarizing (this can take a few minutes)…"
    /usr/bin/xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    /usr/bin/xcrun stapler staple "$DMG"
  fi
fi

say "Done"
echo "  app: $APP"
echo "  dmg: $DMG"
echo "  python: $("$VENV/bin/python" -V) (min macOS $MIN_OS)"
echo
echo "Install with: open \"$DMG\"   then drag DeskGadget to Applications."
