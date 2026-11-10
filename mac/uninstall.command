#!/bin/bash
# DeskGadget for macOS — remove the login item and optionally local data.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA="${DESKGADGET_DATA:-$HOME/Library/Application Support/DeskGadget}"
PLIST="$HOME/Library/LaunchAgents/com.deskgadget.server.plist"
LABEL="com.deskgadget.server"

echo "DeskGadget uninstall"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || launchctl unload "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
echo "  login agent removed"

# the installer may have used a Login Item instead (LaunchAgents not writable)
osascript -e 'tell application "System Events" to delete login item "DeskGadget"' >/dev/null 2>&1 || true
for APP_PATH in "/Applications/DeskGadget.app" "$HOME/Applications/DeskGadget.app"; do
  [ -d "$APP_PATH" ] || continue
  printf "Remove %s? [y/N] " "$APP_PATH"
  read -r answer || answer=""
  case "$answer" in
    y|Y) rm -rf "$APP_PATH"; echo "  removed $APP_PATH" ;;
    *)   echo "  kept $APP_PATH" ;;
  esac
done

printf "Delete paired phones, themes and module settings in %s? [y/N] " "$DATA"
read -r answer || answer=""
case "$answer" in
  y|Y) rm -rf "$DATA"; echo "  data deleted" ;;
  *)   echo "  data kept" ;;
esac

printf "Delete the Python environment (.venv)? [y/N] "
read -r answer || answer=""
case "$answer" in
  y|Y) rm -rf "$ROOT/.venv"; echo "  .venv deleted" ;;
  *)   echo "  .venv kept" ;;
esac

if [ -d "$ROOT/dist/DeskGadget.app" ]; then
  printf "Delete dist/DeskGadget.app? [y/N] "
  read -r answer || answer=""
  case "$answer" in
    y|Y) rm -rf "$ROOT/dist/DeskGadget.app"; echo "  app deleted" ;;
  esac
fi

echo "Done. The folder itself was left in place."
