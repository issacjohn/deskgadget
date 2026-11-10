#!/bin/bash
# DeskGadget for macOS — run in the foreground (development mode).
#
# Data stays inside this folder (server/data) so you can inspect plugins and
# state while working. The installer version keeps data in Application Support.
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/homebrew/share/android-commandlinetools/platform-tools:$PATH"
export DESKGADGET_ROOT="$ROOT/server"
export DESKGADGET_DATA="${DESKGADGET_DATA:-$ROOT/server}"
export DESKGADGET_PORT="${DESKGADGET_PORT:-8787}"

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "No Python environment yet — running the installer first."
  exec "$ROOT/mac/install.command"
fi

echo "DeskGadget (development) on http://localhost:$DESKGADGET_PORT"
echo "Data: $DESKGADGET_DATA    Stop: Ctrl+C"
( sleep 2; open "http://localhost:$DESKGADGET_PORT" >/dev/null 2>&1 || true ) &

exec "$ROOT/.venv/bin/python" -m server.main
