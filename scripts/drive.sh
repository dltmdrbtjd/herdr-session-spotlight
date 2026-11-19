#!/bin/sh
# Drives an open Session Spotlight dialog for manual and scripted checks.
#   scripts/drive.sh open | close | down | up | enter
#   scripts/drive.sh query "프로필 수정"
#   scripts/drive.sh select t3n            (terminal address, session id or key)
#   scripts/drive.sh filter agent codex    (filter kind and value; "default" resets)
#   scripts/drive.sh menu date             (opens a filter chip's menu)
#   scripts/drive.sh shot out.png
set -eu
hex() { printf '%s' "$1" | od -An -tx1 | tr -d ' \n'; }
case "${1:-}" in
  open) herdr-app do mod.open --name session-spotlight ;;
  close) herdr-app do session-spotlight.close ;;
  down|up) herdr-app do "session-spotlight.$1" ;;
  enter) herdr-app do session-spotlight.open ;;
  menu) herdr-app do "session-spotlight.menu-$2" ;;
  query) herdr-app do "session-spotlight.query-$(hex "${2:-}")" ;;
  select) herdr-app do "session-spotlight.select-$2" ;;
  filter)
    v="$3"; [ "$2" = project ] && [ "$v" != default ] && v=$(hex "$v")
    herdr-app do "session-spotlight.filter-$2-$v" ;;
  shot) herdr-app shot "${2:-spotlight.png}" ;;
  *) echo "usage: $0 open|close|down|up|enter|query <text>|select <id>|filter <kind> <value>|shot <file>" >&2; exit 2 ;;
esac
