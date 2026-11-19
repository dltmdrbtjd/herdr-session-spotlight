"""The local index: one SQLite file with an FTS5 trigram index over messages.

Trigram tokenizing makes every substring of three or more characters
searchable, which is what Korean needs ("프로필" inside "프로필을"), and it
is case-insensitive for Latin text. Shorter terms fall back to LIKE scans.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import data_dir, ensure_private_dir

SCHEMA_VERSION = "6"
MACHINE = "local"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources(
  path TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  session_key TEXT,
  size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  offset INTEGER NOT NULL,
  state TEXT NOT NULL,
  indexed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sources_by_session ON sources(session_key);
CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  machine TEXT NOT NULL,
  agent TEXT NOT NULL,
  session_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  title_source TEXT NOT NULL DEFAULT '',
  cwd TEXT NOT NULL DEFAULT '',
  project TEXT NOT NULL DEFAULT '',
  branch TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL DEFAULT 0,
  message_count INTEGER NOT NULL DEFAULT 0,
  first_prompt TEXT NOT NULL DEFAULT '',
  last_prompt TEXT NOT NULL DEFAULT '',
  is_subagent INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  origin TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_by_updated ON sessions(updated_at DESC);
-- Narrow on purpose: a match maps to its session through this table, so its
-- rows must stay small. The text itself lives only in messages_fts.
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY,
  sid INTEGER NOT NULL,
  role TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_by_session ON messages(sid, id);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, tokenize='trigram');
CREATE TABLE IF NOT EXISTS herdr_seen(
  session_key TEXT PRIMARY KEY,
  space_id TEXT NOT NULL DEFAULT '',
  space_name TEXT NOT NULL DEFAULT '',
  tab_id TEXT NOT NULL DEFAULT '',
  tab_name TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  seen_at REAL NOT NULL DEFAULT 0
);
"""


def index_path() -> Path:
    return data_dir() / "index.sqlite3"


def session_key(agent: str, session_id: str, machine: str = MACHINE) -> str:
    return f"{machine}|{agent}|{session_id}"


def connect(readonly: bool = False) -> sqlite3.Connection:
    path = index_path()
    if readonly:
        if not path.exists():
            raise FileNotFoundError(str(path))
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        except sqlite3.Error:
            row = None
        if row is None or row[0] != SCHEMA_VERSION:
            # Built by another version: unusable until the next `index` rebuilds it.
            conn.close()
            raise FileNotFoundError(f"{path} (schema {row[0] if row else '?'}, want {SCHEMA_VERSION})")
    else:
        ensure_private_dir(path.parent)
        fresh = not path.exists()
        conn = sqlite3.connect(str(path), timeout=30)
        if fresh:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        migrate(conn)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    has_meta = conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
    row = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone() if has_meta else None
    if row is not None and row[0] != SCHEMA_VERSION:
        # Older layouts are rebuilt from the agents' logs: the index holds nothing original.
        # herdr_seen is kept: it is the only thing the logs can't give back.
        for name in ("messages_ai", "messages_ad"):
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        for table in ("messages_fts", "messages", "sessions", "sources"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("DELETE FROM meta WHERE key IN ('schema', 'settings_hash')")
        conn.commit()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone() is None:
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema', ?)", (SCHEMA_VERSION,))
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def delete_session(conn: sqlite3.Connection, key: str) -> None:
    row = conn.execute("SELECT id FROM sessions WHERE key=?", (key,)).fetchone()
    if row is None:
        return
    sid = row[0]
    conn.execute("DELETE FROM messages_fts WHERE rowid IN (SELECT id FROM messages WHERE sid=?)", (sid,))
    conn.execute("DELETE FROM messages WHERE sid=?", (sid,))
    conn.execute("DELETE FROM sessions WHERE id=?", (sid,))


def add_messages(conn: sqlite3.Connection, sid: int, rows) -> int:
    """rows: (role, ts, text). Ids are assigned here so text and metadata share one rowid."""
    rows = [r for r in rows if r[2]]
    if not rows:
        return 0
    start = (conn.execute("SELECT max(id) FROM messages").fetchone()[0] or 0) + 1
    ids = range(start, start + len(rows))
    conn.executemany("INSERT INTO messages(id, sid, role, ts) VALUES (?,?,?,?)", [(i, sid, r[0], r[1]) for i, r in zip(ids, rows)])
    conn.executemany("INSERT INTO messages_fts(rowid, text) VALUES (?,?)", [(i, r[2]) for i, r in zip(ids, rows)])
    return len(rows)


def message_texts(conn: sqlite3.Connection, ids) -> dict:
    ids = list(ids)
    out = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for rowid, text in conn.execute(f"SELECT rowid, text FROM messages_fts WHERE rowid IN ({marks})", chunk):
            out[rowid] = text
    return out


def stats(conn: sqlite3.Connection) -> dict:
    sessions = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
    messages = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    by_agent = {r[0]: r[1] for r in conn.execute("SELECT agent, count(*) FROM sessions GROUP BY agent")}
    path = index_path()
    size = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            size += os.path.getsize(str(path) + suffix)
        except OSError:
            pass
    last = get_meta(conn, "last_indexed", "0")
    return {
        "path": str(path),
        "sessions": sessions,
        "messages": messages,
        "agents": by_agent,
        "bytes": size,
        "last_indexed": float(last or 0),
    }


def reset() -> list:
    removed = []
    path = index_path()
    for suffix in ("", "-wal", "-shm", ".lock"):
        p = Path(str(path) + suffix) if suffix != ".lock" else path.with_name("index.lock")
        if p.exists():
            p.unlink()
            removed.append(str(p))
    return removed
