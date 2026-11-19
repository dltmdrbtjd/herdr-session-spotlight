#!/bin/sh
# Copies the mod from this checkout into the running Herdr app (development only).
# Herdr hot-reloads it within a second. Files the app writes there are left alone.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST="${HERDR_APP_HOME:-$HOME/.config/herdr-app}/mods/session-spotlight"
mkdir -p "$DEST"
rsync -a --delete \
  --exclude 'jsconfig.json' --exclude 'gpui-kit.d.ts' --exclude 'herdr.d.ts' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "$HERE/session-spotlight/mods/session-spotlight/" "$DEST/"
echo "synced -> $DEST"
