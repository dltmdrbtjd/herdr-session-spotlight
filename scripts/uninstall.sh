#!/bin/sh
# Removes Session Spotlight from the Herdr app.
#   scripts/uninstall.sh            mod folder + its shortcut
#   scripts/uninstall.sh --purge    also the local index and config
# Claude Code's and Codex's own history is never touched.
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
APP="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
DEST="$APP/mods/session-spotlight"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1
if [ -f "$DEST/engine/spotlight_engine/__init__.py" ]; then
  rm -rf "$DEST"
  echo "removed $DEST"
elif [ -e "$DEST" ]; then
  echo "$DEST isn't Session Spotlight; left alone." >&2
fi
python3 "$HERE/scripts/keys.py" remove
if [ "$PURGE" = 1 ]; then
  DATA="${XDG_DATA_HOME:-$HOME/.local/share}/herdr-session-spotlight"
  CONF="${XDG_CONFIG_HOME:-$HOME/.config}/herdr-session-spotlight"
  rm -rf "$DATA" "$CONF"
  echo "removed $DATA $CONF"
fi
