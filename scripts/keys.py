#!/usr/bin/env python3
"""Adds or removes Session Spotlight's shortcut in Herdr's keys.json, nothing else.

    keys.py add [--key cmd-k]       refuses if the key already does something else
    keys.py check [--key cmd-k]     the same test, changing nothing
    keys.py remove                  removes the binding this script added (recorded at add)
    keys.py remove --key cmd-k      removes that key, only if it opens Session Spotlight

keys.json is backed up next to itself first (keys.json.spotlight-backup-<time>).
A symlinked keys.json (dotfiles) is edited at its target, with its permissions kept.
Runs of this script take turns (a lock), and if anything else changes keys.json while
one runs, nothing is written. Which binding was added is recorded per keys.json file,
so `remove` never takes a binding the person made themselves.
"""

import fcntl
import json
import os
import shutil
import sys
import tempfile
import time

ACTION = "mod.open:session-spotlight"
DEFAULT_KEY = "cmd-k"


def keys_path():
    home = os.environ.get("HERDR_APP_HOME", os.path.expanduser("~/.config/herdr-app"))
    return os.path.realpath(os.path.join(home, "keys.json"))


def spotlight_config():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, "herdr-session-spotlight")
    os.makedirs(path, exist_ok=True)
    return path


def record_path():
    return os.path.join(spotlight_config(), "installed-keys.json")


class Lock:
    """Serializes this script's read-modify-write of keys.json."""

    def __enter__(self):
        self.fd = os.open(os.path.join(spotlight_config(), "keys.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def read(p):
    if not os.path.exists(p):
        return b"", {}
    with open(p, "rb") as f:
        raw = f.read()
    return raw, (json.loads(raw.decode("utf-8")) if raw.strip() else {})


def write(p, snapshot, data):
    """Replaces keys.json atomically, unless something else changed it since `snapshot`."""
    fd, tmp = tempfile.mkstemp(prefix=".keys.json.", dir=os.path.dirname(p))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=True)
            f.write("\n")
        if os.path.exists(p):
            shutil.copymode(p, tmp)
        # Last look right before the swap: the new file is already prepared.
        current, _ = read(p)
        if current != snapshot:
            print("keys.json changed while this ran; nothing written. Run it again.")
            os.unlink(tmp)
            return False
        if os.path.exists(p):
            backup = f"{p}.spotlight-backup-{time.strftime('%Y%m%d-%H%M%S')}"
            n = 1
            while os.path.exists(backup):  # two edits in one second keep both backups
                backup = f"{p}.spotlight-backup-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
                n += 1
            shutil.copy2(p, backup)
            print(f"backup: {backup}")
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def load_records():
    try:
        with open(record_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_records(records):
    tmp = record_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
        f.write("\n")
    os.replace(tmp, record_path())


def main(argv):
    if not argv or argv[0] not in ("add", "check", "remove"):
        print(__doc__)
        return 2
    explicit = argv[argv.index("--key") + 1] if "--key" in argv else None
    key = explicit or DEFAULT_KEY
    p = keys_path()
    with Lock():
        snapshot, data = read(p)
        records = load_records()
        mine = records.get(p, [])  # bindings this script added to this keys.json

        if argv[0] in ("add", "check"):
            for section, binds in data.items():
                if isinstance(binds, dict) and key in binds and binds[key] != ACTION and section in ("global", "terminal"):
                    print(f"{key} is already bound in [{section}] to {binds[key]!r}; not changing it. Pick another with --key.")
                    return 1
            if argv[0] == "check":
                return 0
            if data.get("global", {}).get(key) == ACTION:
                # Already there (maybe the person's own binding): nothing to add, nothing to claim.
                print(f"{key} already opens Session Spotlight")
                return 0
            data.setdefault("global", {})[key] = ACTION
            if not write(p, snapshot, data):
                return 1
            records[p] = [b for b in mine if b != ["global", key]] + [["global", key]]
            save_records(records)
            print(f"added: [global] {key} -> {ACTION}")
            return 0

        # remove: only bindings recorded as added here (or, with --key, that key), and only
        # while they still open Session Spotlight.
        if explicit:
            targets = [[section, explicit] for section in data if isinstance(data[section], dict)]
        else:
            targets = list(mine)
        removed = []
        for section, k in targets:
            binds = data.get(section)
            if isinstance(binds, dict) and binds.get(k) == ACTION:
                del binds[k]
                removed.append([section, k])
        if removed and not write(p, snapshot, data):
            return 1
        left_mine = [b for b in mine if b not in removed and not (explicit and b[1] == explicit)]
        if left_mine:
            records[p] = left_mine
        else:
            records.pop(p, None)
        save_records(records)
        print("removed: " + (", ".join(f"[{a}] {b}" for a, b in removed) if removed else "nothing"))
        left = [f"[{sec}] {k}" for sec, b in data.items() if isinstance(b, dict) for k, v in b.items() if v == ACTION]
        if left:
            print("other bindings to Session Spotlight were left alone: " + ", ".join(left))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
