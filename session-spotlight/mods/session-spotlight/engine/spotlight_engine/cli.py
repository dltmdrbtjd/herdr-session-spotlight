"""Command line for the Session Spotlight engine. Every command prints one JSON object."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Optional

from . import __version__, store
from .config import config_path, data_dir, load_config, write_default_config

# Each command imports what it needs: `search` runs on every keystroke, so it
# must not pay for the indexer's or the process inspector's imports.


def emit(obj: dict) -> int:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


def _json_arg(text: Optional[str], path: Optional[str]):
    if path:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    if text:
        return json.loads(text)
    return None


def _readonly():
    try:
        return store.connect(readonly=True)
    except (FileNotFoundError, sqlite3.OperationalError):
        return None


def cmd_index(args) -> int:
    from .indexer import Busy, run_index

    cfg = load_config()
    try:
        result = run_index(cfg, full=args.full)
    except Busy:
        return emit({"ok": True, "status": "busy", "message": "another indexer is running"})
    result.update(ok=True, status="done", config_errors=cfg.errors)
    return emit(result)


def cmd_search(args) -> int:
    from .search import run_search

    cfg = load_config()
    conn = _readonly()
    live = _json_arg(args.live, args.live_file) or {}
    result = run_search(
        conn, args.query or "", agent=args.agent, project=args.project, since=args.since, until=args.until,
        status=args.status, sort=args.sort, limit=args.limit, live=live, include_subagents=cfg.include_subagents,
    )
    if conn is not None:
        try:
            result["index"] = {
                "ready": True,
                "sessions": conn.execute("SELECT count(*) FROM sessions").fetchone()[0],
                "last_indexed": float(store.get_meta(conn, "last_indexed", "0") or 0),
            }
        finally:
            conn.close()
    else:
        result["index"] = {"ready": False, "sessions": 0, "last_indexed": 0}
    return emit(result)


def cmd_resolve(args) -> int:
    from .live import remember, resolve

    cfg = load_config()
    terminals = _json_arg(args.terminals, args.terminals_file) or []
    result = resolve(terminals, cfg)
    if not args.no_remember:
        try:
            result["remembered"] = remember(terminals, result["terminals"])
        except sqlite3.Error as exc:
            result["remember_error"] = str(exc)
    return emit(result)


def cmd_preview(args) -> int:
    from .search import preview

    conn = _readonly()
    if conn is None:
        return emit({"ok": False, "error": "no_index", "message": "인덱스가 아직 없습니다."})
    try:
        return emit(preview(conn, args.key, args.query or "", args.message))
    finally:
        conn.close()


def cmd_check(args) -> int:
    from .search import check

    conn = _readonly()
    if conn is None:
        return emit({"ok": False, "error": "no_index", "message": "인덱스가 아직 없습니다."})
    try:
        return emit(check(conn, args.key))
    finally:
        conn.close()


def cmd_stats(_args) -> int:
    conn = _readonly()
    if conn is None:
        return emit({"ok": True, "ready": False, "path": str(store.index_path())})
    try:
        out = store.stats(conn)
        out.update(ok=True, ready=True, progress=json.loads(store.get_meta(conn, "progress", "{}") or "{}"))
        return emit(out)
    finally:
        conn.close()


def cmd_reset(args) -> int:
    if not args.yes:
        return emit({"ok": False, "error": "confirm", "message": "pass --yes to delete the index"})
    from .indexer import Busy

    try:
        return emit({"ok": True, "removed": store.reset()})
    except Busy:
        return emit({"ok": False, "error": "busy", "message": "an indexer is running; try again in a moment"})


def cmd_doctor(_args) -> int:
    cfg = load_config()
    fts = True
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize='trigram')")
        c.close()
    except sqlite3.Error:
        fts = False
    try:
        from compression import zstd  # noqa: F401
        zstd_ok = True
    except ImportError:
        zstd_ok = False
    index = store.index_path()
    mode = None
    if index.exists():
        mode = oct(os.stat(index).st_mode & 0o777)
    return emit({
        "ok": fts,
        "version": __version__,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "fts5_trigram": fts,
        "zstd": zstd_ok,
        "index": str(index),
        "index_mode": mode,
        "data_dir": str(data_dir()),
        "config": str(config_path()),
        "config_exists": config_path().exists(),
        "config_errors": cfg.errors,
        "claude_root": str(cfg.claude_root),
        "codex_root": str(cfg.codex_root),
        "agents": cfg.agents,
        "exclude_paths": cfg.exclude_paths,
    })


def cmd_init_config(_args) -> int:
    return emit({"ok": True, "config": str(write_default_config())})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spotlight", description="Herdr Session Spotlight engine")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("index", help="update the local index (incremental)")
    s.add_argument("--full", action="store_true", help="rebuild from scratch")
    s.set_defaults(func=cmd_index)

    s = sub.add_parser("search", help="search sessions")
    s.add_argument("--query", "-q", default="")
    s.add_argument("--agent", default=None)
    s.add_argument("--project", default=None)
    s.add_argument("--since", default=None)
    s.add_argument("--until", default=None)
    s.add_argument("--status", default=None)
    s.add_argument("--sort", default=None)
    s.add_argument("--limit", type=int, default=60)
    s.add_argument("--live", default=None, help="JSON: {terminals: [...]} from the mod")
    s.add_argument("--live-file", default=None)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("resolve", help="map running terminals to sessions")
    s.add_argument("--terminals", default=None, help="JSON list from the mod")
    s.add_argument("--terminals-file", default=None)
    s.add_argument("--no-remember", action="store_true")
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("preview", help="messages around a match")
    s.add_argument("--key", required=True)
    s.add_argument("--query", "-q", default="")
    s.add_argument("--message", type=int, default=None)
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("check", help="can this session be resumed?")
    s.add_argument("--key", required=True)
    s.set_defaults(func=cmd_check)

    sub.add_parser("stats", help="index size and counts").set_defaults(func=cmd_stats)
    s = sub.add_parser("reset", help="delete the index (it is rebuilt from the agents' logs)")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_reset)
    sub.add_parser("doctor", help="environment check").set_defaults(func=cmd_doctor)
    sub.add_parser("init-config", help="write a default config file").set_defaults(func=cmd_init_config)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # the mod shows the message instead of a blank list
        emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
