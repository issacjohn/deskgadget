#!/bin/bash
# Create a local self-signed code-signing identity: "DeskGadget Local".
#
# Why: Ad-hoc signatures (codesign -s -) change on every build. macOS ties
# Accessibility / Screen Recording grants to the app's code identity, so every
# rebuild looks like a different app and the grant is lost. A stable local
# certificate makes TCC grants survive rebuilds on this Mac.
#
# This is for your machine only. Public distribution still needs an Apple
# Developer ID + notarization (`CODESIGN_IDENTITY` / `NOTARY_PROFILE`).
set -euo pipefail

NAME="DeskGadget Local"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if security find-identity -v -p codesigning 2>/dev/null | grep -q "$NAME"; then
  echo "Identity already exists: $NAME"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

/usr/bin/openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout "$TMP/key.pem" -out "$TMP/cert.pem" \
  -subj "/CN=$NAME/O=DeskGadget/C=US" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=critical,codeSigning" \
  >/dev/null 2>&1

/usr/bin/openssl pkcs12 -export \
  -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
  -name "$NAME" -out "$TMP/identity.p12" -passout pass: \
  >/dev/null 2>&1

# importing into the login keychain does not need admin rights; codesign is
# allowed to use the key without an interactive prompt
security import "$TMP/identity.p12" -k "$KEYCHAIN" -P "" \
  -T /usr/bin/codesign >/dev/null

echo "Created identity: $NAME"
security find-identity -v -p codesigning | grep "$NAME" || true
echo
echo "Build with:"
echo "  CODESIGN_IDENTITY=\"$NAME\" ./packaging/build_mac_bundle.sh"
