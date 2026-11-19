"""Incremental indexing.

For every history file the index remembers (size, mtime, byte offset, parser
state). On the next run:

- unchanged file           -> skipped (one stat call)
- file grew (append-only)  -> parsed only from the stored offset
- file shrank / rewritten  -> that session is re-read from the start
- file gone                -> its session leaves the index

Only one indexer runs at a time (an advisory lock next to the index); a
second caller returns at once with status "busy".
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import store
from .adapters import Adapter, CodexAdapter, adapters_for, file_stamp
from .config import Config, ensure_private_dir
from .redact import redact
from .textutil import clip

COMMIT_EVERY_SECONDS = 1.5


class Busy(Exception):
    pass


class IndexLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: Optional[int] = None

    def __enter__(self) -> "IndexLock":
        ensure_private_dir(self.path.parent)
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self.fd)
            self.fd = None
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise Busy() from exc
            raise
        return self

    def __exit__(self, *_exc) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def project_of(cwd: str) -> str:
    cwd = (cwd or "").rstrip("/")
    if not cwd:
        return ""
    home = str(Path.home())
    if cwd == home:
        return "~"
    return os.path.basename(cwd)


def _exclusion_hash(cfg: Config) -> str:
    body = json.dumps([sorted(cfg.exclude_paths), cfg.index_assistant, cfg.max_message_chars, cfg.include_subagents, cfg.include_archived])
    return hashlib.sha1(body.encode()).hexdigest()


def run_index(cfg: Config, full: bool = False, progress=None) -> dict:
    started = time.time()
    lock_path = store.index_path().with_name("index.lock")
    with IndexLock(lock_path):
        conn = store.connect()
        try:
            return _index(conn, cfg, full, started, progress)
        finally:
            conn.close()


def _index(conn, cfg: Config, full: bool, started: float, progress) -> dict:
    counts = {"files": 0, "unchanged": 0, "appended": 0, "reread": 0, "removed": 0, "excluded": 0, "skipped": 0}
    settings_hash = _exclusion_hash(cfg)
    if full or store.get_meta(conn, "settings_hash") != settings_hash:
        # What gets indexed changed: everything is read again.
        conn.execute("DELETE FROM sources")
        conn.execute("DELETE FROM messages_fts")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")
        store.set_meta(conn, "settings_hash", settings_hash)
        conn.commit()

    adapters = adapters_for(cfg)
    enabled = {a.agent for a in adapters}
    known: Dict[str, object] = {}
    for row in conn.execute("SELECT path, agent, session_key, size, mtime_ns, offset, state FROM sources"):
        known[row["path"]] = row

    seen = set()
    last_commit = time.time()
    plan = []
    for adapter in adapters:
        if isinstance(adapter, CodexAdapter):
            adapter.load_thread_names(cfg)
        for path in adapter.discover(cfg):
            plan.append((adapter, path))
    total = len(plan)

    for n, (adapter, path) in enumerate(plan, 1):
        key = str(path)
        seen.add(key)
        counts["files"] += 1
        stamp = file_stamp(path)
        if stamp is None:
            continue
        row = known.get(key)
        if row is not None and (row["size"], row["mtime_ns"]) == stamp:
            counts["unchanged"] += 1
            continue
        mode = _index_file(conn, cfg, adapter, path, stamp, row)
        counts[mode] = counts.get(mode, 0) + 1
        if time.time() - last_commit > COMMIT_EVERY_SECONDS:
            store.set_meta(conn, "progress", json.dumps({"done": n, "total": total}))
            conn.commit()
            last_commit = time.time()
            if progress:
                progress(n, total)

    # History files that are gone take their sessions with them.
    for key, row in known.items():
        if key in seen or row["agent"] not in enabled:
            continue
        if row["session_key"]:
            store.delete_session(conn, row["session_key"])
        conn.execute("DELETE FROM sources WHERE path=?", (key,))
        counts["removed"] += 1
    # Agents switched off in the config leave too.
    for row in conn.execute("SELECT DISTINCT agent FROM sessions").fetchall():
        if row[0] not in enabled:
            for k in [r[0] for r in conn.execute("SELECT key FROM sessions WHERE agent=?", (row[0],))]:
                store.delete_session(conn, k)
            conn.execute("DELETE FROM sources WHERE agent=?", (row[0],))

    # Codex names threads in a separate index; a rename touches no rollout file.
    for adapter in adapters:
        if isinstance(adapter, CodexAdapter) and adapter.thread_names:
            for sid, name in adapter.thread_names.items():
                name = redact(name)
                conn.execute(
                    "UPDATE sessions SET title=?, title_source='name' WHERE agent='codex' AND session_id=? AND title<>?",
                    (name, sid, name),
                )

    store.set_meta(conn, "last_indexed", str(time.time()))
    store.set_meta(conn, "progress", json.dumps({"done": total, "total": total}))
    conn.commit()
    result = store.stats(conn)
    result.update(counts)
    result["took_ms"] = int((time.time() - started) * 1000)
    return result


def _index_file(conn, cfg: Config, adapter: Adapter, path: Path, stamp, row) -> str:
    size, mtime_ns = stamp
    append = (
        row is not None
        and row["session_key"]
        and adapter.appendable(path)
        and size >= row["size"]
        and row["offset"] <= size
    )
    if append:
        try:
            state = json.loads(row["state"])
        except ValueError:
            append = False
    if not append:
        state = adapter.new_state(path)
        offset = 0
    else:
        offset = row["offset"]

    pending: List[tuple] = []

    def emit(role: str, ts: float, text: str) -> None:
        if role == "assistant" and not cfg.index_assistant:
            return
        pending.append((role, ts, clip(redact(text.strip()), cfg.max_message_chars)))

    end = offset
    try:
        for record, position in adapter.records(path, offset):
            adapter.feed(state, record, emit)
            end = position or end
    except OSError:
        return "skipped"
    if not adapter.appendable(path):
        end = size

    meta = adapter.meta(state, path)
    state_json = json.dumps(state, ensure_ascii=False)
    now = time.time()

    def remember(session_key_value):
        conn.execute(
            "INSERT INTO sources(path, agent, session_key, size, mtime_ns, offset, state, indexed_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET agent=excluded.agent, session_key=excluded.session_key, size=excluded.size, "
            "mtime_ns=excluded.mtime_ns, offset=excluded.offset, state=excluded.state, indexed_at=excluded.indexed_at",
            (str(path), adapter.agent, session_key_value, size, mtime_ns, end, state_json, now),
        )

    old_key = row["session_key"] if row is not None else None
    if meta is None:
        if old_key:
            store.delete_session(conn, old_key)
        remember(None)
        return "skipped"
    if meta["is_subagent"] and not cfg.include_subagents:
        if old_key:
            store.delete_session(conn, old_key)
        remember(None)
        return "skipped"
    if cfg.excluded(meta["cwd"]):
        if old_key:
            store.delete_session(conn, old_key)
        remember(None)
        return "excluded"

    key = store.session_key(adapter.agent, meta["session_id"])
    existing = conn.execute("SELECT source_path, updated_at FROM sessions WHERE key=?", (key,)).fetchone()
    if existing is not None and existing["source_path"] != str(path) and os.path.exists(existing["source_path"]):
        # The same session in two files (a copy, an archive): the newer one wins.
        if existing["updated_at"] >= (meta["updated_at"] or 0):
            remember(None)
            return "skipped"
        append = False
    if append and old_key != key:
        # The file now names another session: read it whole.
        store.delete_session(conn, old_key)
        return _index_file(conn, cfg, adapter, path, stamp, None)
    if not append:
        if old_key and old_key != key:
            store.delete_session(conn, old_key)
        store.delete_session(conn, key)

    updated = meta["updated_at"] or (mtime_ns / 1e9)
    created = meta["created_at"] or updated
    conn.execute(
        "INSERT INTO sessions(key, machine, agent, session_id, title, title_source, cwd, project, branch, created_at, updated_at, "
        "message_count, first_prompt, last_prompt, is_subagent, archived, origin, version, source_path) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET title=excluded.title, title_source=excluded.title_source, cwd=excluded.cwd, "
        "project=excluded.project, branch=excluded.branch, created_at=excluded.created_at, updated_at=excluded.updated_at, "
        "message_count=excluded.message_count, first_prompt=excluded.first_prompt, last_prompt=excluded.last_prompt, "
        "is_subagent=excluded.is_subagent, archived=excluded.archived, origin=excluded.origin, version=excluded.version, "
        "source_path=excluded.source_path",
        (
            key, store.MACHINE, adapter.agent, meta["session_id"], redact(meta["title"]), meta["title_source"], meta["cwd"],
            project_of(meta["cwd"]), meta["branch"], created, updated, meta["message_count"],
            redact(meta["first_prompt"]), redact(meta["last_prompt"]), int(meta["is_subagent"]), int(meta["archived"]),
            meta["origin"], meta["version"], str(path),
        ),
    )
    sid = conn.execute("SELECT id FROM sessions WHERE key=?", (key,)).fetchone()[0]
    store.add_messages(conn, sid, pending)
    remember(key)
    return "appended" if append else "reread"
