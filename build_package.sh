#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ADDON_XML="$ROOT_DIR/addon.xml"
DIST_DIR="$ROOT_DIR/dist"
STAGE_DIR="$DIST_DIR/script.aspirando-kodi"

if [[ ! -f "$ADDON_XML" ]]; then
  echo "No se encontro addon.xml en $ROOT_DIR" >&2
  exit 1
fi

VERSION="$(grep -m 1 '^<addon ' "$ADDON_XML" | sed -n 's/.*version="\([^"]*\)".*/\1/p')"
if [[ -z "$VERSION" ]]; then
  echo "No se pudo extraer la version desde addon.xml" >&2
  exit 1
fi

ZIP_PATH="$DIST_DIR/script.aspirando-kodi-$VERSION.zip"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

copy_item() {
  local src="$1"
  local dst="$2"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    cp -a "$src/." "$dst/"
  else
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

copy_item "$ROOT_DIR/addon.xml" "$STAGE_DIR/addon.xml"
copy_item "$ROOT_DIR/default.py" "$STAGE_DIR/default.py"
copy_item "$ROOT_DIR/service.py" "$STAGE_DIR/service.py"
copy_item "$ROOT_DIR/buffering.py" "$STAGE_DIR/buffering.py"
copy_item "$ROOT_DIR/updater.py" "$STAGE_DIR/updater.py"
copy_item "$ROOT_DIR/LICENSE" "$STAGE_DIR/LICENSE"
copy_item "$ROOT_DIR/README.md" "$STAGE_DIR/README.md"
copy_item "$ROOT_DIR/icon.png" "$STAGE_DIR/icon.png"
copy_item "$ROOT_DIR/fanart.png" "$STAGE_DIR/fanart.png"
copy_item "$ROOT_DIR/logo.png" "$STAGE_DIR/logo.png"
copy_item "$ROOT_DIR/resources" "$STAGE_DIR/resources"

rm -f "$ZIP_PATH"
(
  cd "$DIST_DIR"
  zip -qr "$(basename "$ZIP_PATH")" "script.aspirando-kodi"
)

echo "$ZIP_PATH"