"""Herdr Live Sessions: which history session each running terminal holds.

Never by title or folder: by process.

- Claude Code writes ~/.claude/sessions/<pid>.json with its sessionId. The
  file's procStart must equal the process's own start time, so a stale file
  left by a dead process whose pid was reused never claims a terminal.
- Codex keeps its rollout file open while it runs; lsof on the codex process
  names the file, and the file name carries the session id.
- `... resume <uuid>` / `--resume <uuid>` in the foreground command is the
  fallback for both.

The mod hands in Herdr's own terminal list (address, pid, foreground pid and
argv, labels), so nothing here talks to herdr-core.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import store

WRAPPERS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "env", "-zsh", "-bash"}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class ProcessTable:
    def __init__(self, rows: Dict[int, Tuple[int, str, str]]) -> None:
        # pid -> (ppid, lstart, command)
        self.rows = rows
        self.children: Dict[int, List[int]] = {}
        for pid, (ppid, _, _) in rows.items():
            self.children.setdefault(ppid, []).append(pid)

    @classmethod
    def snapshot(cls) -> "ProcessTable":
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "pid=,ppid=,lstart=,comm="], capture_output=True, text=True, timeout=5,
                env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},  # Claude records procStart like this: C locale, UTC
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return cls({})
        rows: Dict[int, Tuple[int, str, str]] = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                pid, ppid = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            lstart = " ".join(parts[2:7])
            comm = " ".join(parts[7:])
            rows[pid] = (ppid, lstart, comm)
        return cls(rows)

    def descendants(self, pid: int, limit: int = 64) -> List[int]:
        out, stack = [], [pid]
        while stack and len(out) < limit:
            p = stack.pop()
            for c in self.children.get(p, []):
                out.append(c)
                stack.append(c)
        return out

    def started(self, pid: int) -> Optional[str]:
        row = self.rows.get(pid)
        return row[1] if row else None

    def command(self, pid: int) -> str:
        row = self.rows.get(pid)
        return row[2] if row else ""


def _same_start(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return " ".join(a.split()) == " ".join(b.split())


def claude_session_for(pids: List[int], claude_root: Path, procs: ProcessTable) -> Optional[str]:
    sessions = claude_root / "sessions"
    for pid in pids:
        path = sessions / f"{pid}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not data.get("sessionId"):
            continue
        recorded = data.get("procStart")
        actual = procs.started(pid)
        if recorded and actual and not _same_start(recorded, actual):
            continue  # a dead process's file; this pid belongs to someone else now
        if actual is None:
            continue  # not running
        return str(data["sessionId"])
    return None


def codex_sessions_by_pid(pids: List[int], codex_root: Path) -> Dict[int, str]:
    if not pids:
        return {}
    try:
        out = subprocess.run(
            ["lsof", "-a", "-p", ",".join(str(p) for p in pids), "-Fpn"],
            capture_output=True, text=True, timeout=8, env={**os.environ, "LC_ALL": "C"},
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    root = str(codex_root)
    found: Dict[int, str] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("p"):
            try:
                current = int(line[1:])
            except ValueError:
                current = None
        elif line.startswith("n") and current is not None:
            path = line[1:]
            if path.startswith(root) and "/rollout-" in path and path.endswith(".jsonl"):
                m = UUID.search(path.rsplit("/", 1)[-1])
                if m:
                    found[current] = m.group(0)
    return found


def argv_session(argv: List[str]) -> Optional[str]:
    words = [str(a) for a in argv or []]
    for i, word in enumerate(words):
        if word in ("--resume", "-r", "resume", "--session-id") and i + 1 < len(words) and UUID.fullmatch(words[i + 1]):
            return words[i + 1]
        if word.startswith("--resume=") and UUID.fullmatch(word.split("=", 1)[1]):
            return word.split("=", 1)[1]
    return None


def agent_of(t: dict) -> str:
    """claude / codex / the program key Herdr reports. What the agent reports and Herdr's
    program table come first; argv is read by its program's name only, never by substring
    (a folder named claude-501 in an argument says nothing about the program)."""
    app = (t.get("app") or "").lower()
    program = (t.get("program") or "").lower()
    if app in ("claude-code", "claude") or program == "claude":
        return "claude"
    if app == "codex" or program == "codex":
        return "codex"
    if program and program not in ("program", "shell", "agent"):
        return program
    argv = [str(a) for a in (t.get("fg_argv") or [])]
    names = [w.rsplit("/", 1)[-1].lower() for w in argv]
    # The program itself, or the one a launcher shell runs (`zsh -lic '"$@"…' zsh claude …`).
    look = names[:1]
    if names and names[0] in WRAPPERS:
        look = [n for n in names[1:8] if not n.startswith("-")]
    for name in look:
        if name in ("claude", "claude-code"):
            return "claude"
        if name == "codex":
            return "codex"
    return app or program or "other"


def resolve(terminals: List[dict], cfg, procs: Optional[ProcessTable] = None) -> dict:
    started = time.perf_counter()
    procs = procs or ProcessTable.snapshot()
    out: List[dict] = []
    codex_wanted: Dict[str, List[int]] = {}
    for t in terminals:
        address = t.get("address")
        if not address:
            continue
        agent = agent_of(t)
        pids: List[int] = []
        for value in (t.get("fg_pid"), t.get("pid")):
            try:
                if value:
                    pids.append(int(value))
            except (TypeError, ValueError):
                pass
        tree: List[int] = []
        for p in pids:
            if p not in tree:
                tree.append(p)
            for d in procs.descendants(p):
                if d not in tree:
                    tree.append(d)
        entry = {"address": address, "agent": agent, "session_id": None, "method": None}
        if agent == "claude":
            sid = claude_session_for(tree, cfg.claude_root, procs)
            if sid:
                entry.update(session_id=sid, method="claude-pid-file")
        elif agent == "codex":
            codex_wanted[address] = [p for p in tree if "codex" in procs.command(p).lower()] or tree[:1]
        if not entry["session_id"]:
            sid = argv_session(t.get("fg_argv") or [])
            if sid and agent in ("claude", "codex"):
                entry.update(session_id=sid, method="argv")
        out.append(entry)
    if codex_wanted:
        all_pids = sorted({p for ps in codex_wanted.values() for p in ps})
        by_pid = codex_sessions_by_pid(all_pids, cfg.codex_root)
        for entry in out:
            pids = codex_wanted.get(entry["address"])
            if not pids:
                continue
            for p in pids:
                if p in by_pid:
                    entry.update(session_id=by_pid[p], method="codex-open-rollout")
                    break
    return {"ok": True, "terminals": out, "took_ms": round((time.perf_counter() - started) * 1000, 1)}


def remember(terminals: List[dict], resolved: List[dict]) -> int:
    """Notes which Herdr space each running session was seen in, for project filters and resume later."""
    by_address = {t.get("address"): t for t in terminals}
    rows = []
    now = time.time()
    for r in resolved:
        if not r.get("session_id") or r.get("agent") not in ("claude", "codex"):
            continue
        t = by_address.get(r["address"]) or {}
        rows.append((
            store.session_key(r["agent"], r["session_id"]), t.get("space_id") or "", t.get("space_name") or "",
            t.get("tab_id") or "", t.get("tab_name") or "", r["address"], now,
        ))
    if not rows:
        return 0
    conn = store.connect()
    try:
        conn.executemany(
            "INSERT INTO herdr_seen(session_key, space_id, space_name, tab_id, tab_name, address, seen_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(session_key) DO UPDATE SET space_id=excluded.space_id, space_name=excluded.space_name, "
            "tab_id=excluded.tab_id, tab_name=excluded.tab_name, address=excluded.address, seen_at=excluded.seen_at",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)
