#!/usr/bin/env python3
"""Adds or removes Session Spotlight's shortcut in Herdr's keys.json, nothing else.

    keys.py add [--key cmd-shift-k]     refuses if the key already does something else
    keys.py check [--key cmd-shift-k]   the same test, changing nothing
    keys.py remove                      removes only bindings that open session-spotlight

The file is backed up next to itself first (keys.json.spotlight-backup-<time>).
"""

import json
import os
import shutil
import sys
import time

ACTION = "mod.open:session-spotlight"


def path():
    return os.path.join(os.environ.get("HERDR_APP_HOME", os.path.expanduser("~/.config/herdr-app")), "keys.json")


def load(p):
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(p, data):
    if os.path.exists(p):
        backup = f"{p}.spotlight-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(p, backup)
        print(f"backup: {backup}")
    tmp = p + ".spotlight-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")
    os.replace(tmp, p)


def main(argv):
    if not argv or argv[0] not in ("add", "check", "remove"):
        print(__doc__)
        return 2
    key = "cmd-shift-k"
    if "--key" in argv:
        key = argv[argv.index("--key") + 1]
    p = path()
    data = load(p)
    if argv[0] in ("add", "check"):
        for section, binds in data.items():
            if isinstance(binds, dict) and key in binds and binds[key] != ACTION and section in ("global", "terminal"):
                print(f"{key} is already bound in [{section}] to {binds[key]!r}; not changing it. Pick another with --key.")
                return 1
        if argv[0] == "check":
            return 0
        if data.get("global", {}).get(key) == ACTION:
            print(f"{key} already opens Session Spotlight")
            return 0
        data.setdefault("global", {})[key] = ACTION
        save(p, data)
        print(f"added: [global] {key} -> {ACTION}")
        return 0
    removed = []
    for section, binds in data.items():
        if isinstance(binds, dict):
            for k in [k for k, v in binds.items() if v == ACTION]:
                del binds[k]
                removed.append(f"[{section}] {k}")
    if removed:
        save(p, data)
    print("removed: " + (", ".join(removed) if removed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
