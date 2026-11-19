#!/bin/sh
# Installs Session Spotlight into the Herdr app on this computer.
#   scripts/install.sh [--key cmd-k] [--no-key]
# - copies session-spotlight/mods/session-spotlight to ~/.config/herdr-app/mods/
#   (refuses to replace a folder of that name that it didn't install)
# - adds one shortcut to keys.json (backed up first; refuses to take a key in use)
# - checks the environment and the mod; the index is built on the first open.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
APP="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
DEST="$APP/mods/session-spotlight"
KEY=cmd-k
ADD_KEY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --key) KEY="$2"; shift 2 ;;
    --no-key) ADD_KEY=0; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
command -v python3 >/dev/null || { echo "python3 is required (3.9+)" >&2; exit 1; }
[ -d "$APP" ] || { echo "Herdr app home not found: $APP" >&2; exit 1; }
# Refuse before copying anything if the shortcut is taken.
if [ "$ADD_KEY" = 1 ]; then python3 "$HERE/scripts/keys.py" check --key "$KEY"; fi
if [ -e "$DEST" ] && [ ! -f "$DEST/engine/spotlight_engine/__init__.py" ]; then
  echo "$DEST exists and isn't Session Spotlight; not touching it." >&2
  exit 1
fi
mkdir -p "$DEST"
rsync -a --delete \
  --exclude 'jsconfig.json' --exclude 'gpui-kit.d.ts' --exclude 'herdr.d.ts' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  "$HERE/session-spotlight/mods/session-spotlight/" "$DEST/"
echo "mod: $DEST"
python3 -B "$DEST/engine/spotlight.py" doctor
if [ "$ADD_KEY" = 1 ]; then python3 "$HERE/scripts/keys.py" add --key "$KEY"; fi
if command -v herdr-app >/dev/null; then herdr-app check "$DEST"; fi
echo "Done. Press $KEY in Herdr (or run: herdr-app do mod.open --name session-spotlight)."
