#!/bin/bash
# Publish a DeskGadget MAC release and always point at the latest stable APK.
#
#   ./packaging/release_mac.sh 1.0.10 /tmp/notes.md [path/to.dmg]
#
# Notes are prefixed with the Android app link, resolved from the repo's
# **latest non-prerelease** release. MAC releases must stay --latest=false:
# that keeps `releases/latest/download/DeskGadget.apk` pointing at the Android
# build instead of a mac DMG.
set -euo pipefail

VERSION="${1:?usage: release_mac.sh <version> <notes-file> [dmg]}"
NOTES="${2:?notes file with the release body}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DMG="${3:-$ROOT/dist/DeskGadget-MAC-$VERSION-arm64.dmg}"
TAG="mac-v$VERSION"
REPO="${DESKGADGET_REPO:-issacjohn/deskgadget}"

APK_TAG="$(gh api "repos/$REPO/releases/latest" --jq .tag_name)"
APK_URL="https://github.com/$REPO/releases/latest/download/DeskGadget.apk"

if [ ! -f "$DMG" ]; then
  echo "No DMG at $DMG — build it with packaging/build_mac_bundle.sh first." >&2
  exit 1
fi

MERGED="$(mktemp)"
trap 'rm -f "$MERGED"' EXIT
{
  echo "**Android app — latest stable:** [DeskGadget.apk ($APK_TAG)]($APK_URL)"
  echo
  echo "The same APK works with every DeskGadget server; nothing Android-side is macOS-specific."
  echo
  cat "$NOTES"
} > "$MERGED"

gh release create "$TAG" "$DMG" \
  --repo "$REPO" \
  --title "DeskGadget MAC" \
  --notes-file "$MERGED" \
  --target mac \
  --latest=false

echo "Released $TAG with $DMG"
echo "APK link: $APK_URL ($APK_TAG)"
