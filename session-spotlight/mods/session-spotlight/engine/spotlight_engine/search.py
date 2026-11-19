"""Session Search Service: filters, ranking, snippets and previews.

A query is words (or "quoted phrases") plus optional operators:

    project:acme-web  agent:claude  after:2026-11-01  before:2026-11-10
    status:running  sort:created

Every word must match somewhere in a session (AND): its title, Herdr space or
project, branch, folder, agent, first prompt, or any indexed message.
Matching is case-insensitive substring matching, so Korean particles don't
get in the way ("프로필" finds "프로필을").
"""

from __future__ import annotations

import math
import os
import re
import shlex
import sqlite3
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import store
from .textutil import contains_all, excerpt, fold, highlight, snippet, squash

AGENTS = {"claude": "Claude Code", "codex": "Codex"}
AGENT_ALIASES = {
    "claude": "claude", "claude-code": "claude", "cc": "claude",
    "codex": "codex", "openai": "codex",
    "other": "other", "others": "other", "etc": "other", "기타": "other",
}
SORTS = ("relevance", "recent", "created", "oldest")
STATUS_ALIASES = {"running": "running", "live": "running", "실행": "running", "실행중": "running",
                  "ended": "ended", "done": "ended", "closed": "ended", "종료": "ended", "종료됨": "ended"}

# Field weights for a word found in that field.
W_TITLE, W_SPACE, W_PROMPT, W_BRANCH, W_CWD, W_AGENT = 10.0, 6.0, 3.0, 3.0, 2.0, 2.0


class Query:
    def __init__(self) -> None:
        self.terms: List[str] = []
        self.project: Optional[str] = None
        self.agent: Optional[str] = None
        self.after: Optional[float] = None
        self.before: Optional[float] = None
        self.status: Optional[str] = None
        self.sort: Optional[str] = None
        self.ignored: List[str] = []

    def as_dict(self) -> dict:
        return {
            "terms": self.terms, "project": self.project, "agent": self.agent, "after": self.after,
            "before": self.before, "status": self.status, "sort": self.sort, "ignored": self.ignored,
        }


def start_of_day(ts: float) -> float:
    d = datetime.fromtimestamp(ts)
    return datetime(d.year, d.month, d.day).timestamp()


def parse_date(value: str, now: float) -> Optional[float]:
    """today, yesterday, 7d, 2w, 3m, or YYYY-MM-DD (local midnight)."""
    v = (value or "").strip().lower()
    if not v or v in ("all", "전체", "any"):
        return None
    if v in ("today", "오늘"):
        return start_of_day(now)
    if v in ("yesterday", "어제"):
        return start_of_day(now) - 86400
    m = re.fullmatch(r"(\d+)\s*([dwmy])", v)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = {"d": 1, "w": 7, "m": 30, "y": 365}[unit] * n
        return start_of_day(now) - (days - 1) * 86400
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m", "%Y%m%d"):
        try:
            return datetime.strptime(v, fmt).timestamp()
        except ValueError:
            continue
    return None


def _split(text: str) -> List[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.replace('"', " ").split()


def parse_query(text: str, now: Optional[float] = None) -> Query:
    now = now or time.time()
    q = Query()
    for token in _split(text or ""):
        if ":" in token and not token.startswith(":"):
            name, _, value = token.partition(":")
            name = name.lower()
            if value:
                if name in ("project", "space", "p", "proj", "프로젝트"):
                    q.project = value
                    continue
                if name in ("agent", "a", "에이전트"):
                    q.agent = AGENT_ALIASES.get(value.lower(), value.lower())
                    continue
                if name in ("after", "since", "from", "이후"):
                    parsed = parse_date(value, now)
                    if parsed is not None:
                        q.after = parsed
                    else:
                        q.ignored.append(token)
                    continue
                if name in ("before", "until", "to", "이전"):
                    parsed = parse_date(value, now)
                    if parsed is not None:
                        q.before = parsed + (86400 if re.fullmatch(r"\d{4}[-/.]?\d{2}[-/.]?\d{2}", value) else 0)
                    else:
                        q.ignored.append(token)
                    continue
                if name in ("status", "is", "상태"):
                    status = STATUS_ALIASES.get(value.lower())
                    if status:
                        q.status = status
                    else:
                        q.ignored.append(token)
                    continue
                if name in ("sort", "정렬"):
                    if value.lower() in SORTS:
                        q.sort = value.lower()
                    else:
                        q.ignored.append(token)
                    continue
        term = fold(token.strip())
        if term and term not in q.terms:
            q.terms.append(term)
    return q


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _fts_phrase(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


class Hit:
    __slots__ = ("count", "last_id")

    def __init__(self, count: int = 0, last_id: int = 0) -> None:
        self.count = count
        self.last_id = last_id


class Searcher:
    def __init__(self, conn: Optional[sqlite3.Connection], include_subagents: bool = False) -> None:
        self.conn = conn
        self.include_subagents = include_subagents
        self.key_of: Dict[int, str] = {}
        self.sid_of: Dict[str, int] = {}

    # -- data -------------------------------------------------------------

    def sessions(self) -> List[dict]:
        if self.conn is None:
            return []
        where = "" if self.include_subagents else "WHERE s.is_subagent=0"
        rows = self.conn.execute(
            "SELECT s.*, h.space_id AS seen_space_id, h.space_name AS seen_space_name, h.tab_name AS seen_tab_name, "
            "h.seen_at AS seen_at FROM sessions s LEFT JOIN herdr_seen h ON h.session_key=s.key " + where
        ).fetchall()
        out = [dict(r) for r in rows]
        for s in out:
            self.key_of[s["id"]] = s["key"]
            self.sid_of[s["key"]] = s["id"]
        return out

    def _sid(self, key: str) -> Optional[int]:
        if key in self.sid_of:
            return self.sid_of[key]
        row = self.conn.execute("SELECT id FROM sessions WHERE key=?", (key,)).fetchone() if self.conn else None
        return row[0] if row else None

    def message_hits(self, term: str, keys: Optional[Iterable[str]] = None) -> Dict[str, Hit]:
        """Sessions whose messages hold `term`: how often, and the newest such message."""
        if self.conn is None:
            return {}
        if len(term) >= 3:
            sql = (
                "SELECT m.sid, count(*), max(m.id) FROM messages_fts f JOIN messages m ON m.id=f.rowid "
                "WHERE messages_fts MATCH ? GROUP BY m.sid"
            )
            args: Tuple = (_fts_phrase(term),)
        else:
            # Trigrams can't index one or two characters: scan, within the sessions still in play when that's few.
            sids = [self.sid_of[k] for k in keys if k in self.sid_of] if keys is not None else None
            if sids is not None and len(sids) <= 900:
                if not sids:
                    return {}
                marks = ",".join("?" * len(sids))
                sql = (
                    "SELECT m.sid, count(*), max(m.id) FROM messages m JOIN messages_fts f ON f.rowid=m.id "
                    "WHERE m.sid IN (" + marks + ") AND instr(lower(f.text), ?) > 0 GROUP BY m.sid"
                )
                args = tuple(sids) + (term,)
            else:
                sql = (
                    "SELECT m.sid, count(*), max(m.id) FROM messages_fts f JOIN messages m ON m.id=f.rowid "
                    "WHERE instr(lower(f.text), ?) > 0 GROUP BY m.sid"
                )
                args = (term,)
        out: Dict[str, Hit] = {}
        try:
            for sid, count, last in self.conn.execute(sql, args):
                key = self.key_of.get(sid)
                if key:
                    out[key] = Hit(count, last)
        except sqlite3.OperationalError:
            return {}
        return out

    def best_message(self, key: str, terms: Sequence[str]) -> Optional[dict]:
        """The newest message holding the most query words."""
        if self.conn is None or not terms:
            return None
        sid = self._sid(key)
        if sid is None:
            return None
        meta = self.conn.execute("SELECT id, role, ts FROM messages WHERE sid=? ORDER BY id DESC LIMIT 4000", (sid,)).fetchall()
        texts = store.message_texts(self.conn, [r[0] for r in meta])
        best, best_n = None, 0
        for r in meta:  # newest first, so ties keep the newest
            text = texts.get(r[0], "")
            n = contains_all(text, terms)
            if n > best_n:
                best, best_n = {"id": r[0], "role": r[1], "ts": r[2], "text": text}, n
                if n == len(terms):
                    break
        return best


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


_HOME = os.path.expanduser("~").rstrip("/")


def _short_cwd(cwd: str) -> str:
    """The folder below home: a word in /Users/<name>/ shouldn't match every session."""
    if cwd == _HOME:
        return "~"
    return cwd[len(_HOME) + 1:] if cwd.startswith(_HOME + "/") else cwd


def _live_rows(live: dict) -> List[dict]:
    return [t for t in (live or {}).get("terminals", []) if isinstance(t, dict) and t.get("address")]


def merge_live(sessions: List[dict], live: dict) -> List[dict]:
    """Marks indexed sessions that run in a Herdr terminal, and adds terminals with no indexed session."""
    by_key = {(s["agent"], s["session_id"]): s for s in sessions}
    extra: List[dict] = []
    for t in _live_rows(live):
        agent = t.get("agent") or "other"
        sid = t.get("session_id")
        running = {
            "address": t.get("address"), "space_id": t.get("space_id") or "", "space_name": t.get("space_name") or "",
            "tab_id": t.get("tab_id") or "", "tab_name": t.get("tab_name") or "", "status": t.get("status") or "",
            "pane": t.get("pane") or "", "title": t.get("title") or "",
        }
        changed = _num(t.get("changed_ms")) / 1000.0
        target = by_key.get((agent, sid)) if sid else None
        if target is not None:
            # Two terminals can't run one session, but the first one wins if they claim to.
            if not target.get("running"):
                target["running"] = running
                target["updated_at"] = max(_num(target.get("updated_at")), changed)
            continue
        created = _num(t.get("created_ms")) / 1000.0
        extra.append({
            "key": f"live|{t.get('address')}",
            "kind": "live",
            "machine": "local",
            "agent": agent,
            "agent_name": t.get("program") or AGENTS.get(agent, agent),
            "session_id": sid or "",
            "title": t.get("title") or t.get("tab_name") or t.get("program") or t.get("address"),
            "title_source": "terminal",
            "cwd": t.get("cwd") or "",
            "project": os.path.basename((t.get("cwd") or "").rstrip("/")),
            "branch": t.get("branch") or "",
            "created_at": created,
            "updated_at": max(changed, created),
            "message_count": 0,
            "first_prompt": "",
            "last_prompt": "",
            "is_subagent": 0,
            "archived": 0,
            "origin": "herdr",
            "source_path": "",
            "running": running,
        })
    return sessions + extra


def agent_bucket(agent: str) -> str:
    return agent if agent in AGENTS else "other"


def space_of(s: dict) -> str:
    running = s.get("running") or {}
    return running.get("space_name") or s.get("seen_space_name") or ""


def run_search(
    conn: Optional[sqlite3.Connection],
    text: str = "",
    *,
    agent: Optional[str] = None,
    project: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = None,
    limit: int = 60,
    live: Optional[dict] = None,
    include_subagents: bool = False,
    now: Optional[float] = None,
) -> dict:
    started = time.perf_counter()
    now = now or time.time()
    q = parse_query(text, now)
    searcher = Searcher(conn, include_subagents)
    rows = merge_live(searcher.sessions(), live or {})

    # Filters: chips first, then operators typed in the field narrow further.
    want_agent = AGENT_ALIASES.get((q.agent or agent or "").lower(), (q.agent or agent or "").lower()) or None
    if want_agent in ("all", ""):
        want_agent = None
    after = q.after if q.after is not None else (parse_date(since, now) if since else None)
    before = q.before if q.before is not None else (parse_date(until, now) + 86400 if until and parse_date(until, now) else None)
    want_status = q.status or (status if status in ("running", "ended") else None)
    want_project = fold(q.project or project or "") or None

    def keep(s: dict) -> bool:
        if want_agent and agent_bucket(s["agent"]) != want_agent:
            return False
        if want_status == "running" and not s.get("running"):
            return False
        if want_status == "ended" and s.get("running"):
            return False
        updated = _num(s.get("updated_at"))
        if after is not None and updated < after:
            return False
        if before is not None and updated >= before:
            return False
        if want_project:
            names = {fold(s.get("project") or ""), fold(space_of(s))}
            if want_project not in names and not any(want_project in n for n in names if n):
                return False
        return True

    candidates = [s for s in rows if keep(s)]
    order = q.sort or (sort if sort in SORTS else None) or ("relevance" if q.terms else "recent")

    scored: List[Tuple[float, dict]] = []
    msg_hits: Dict[str, Dict[str, Hit]] = {}
    if q.terms:
        alive = {s["key"]: s for s in candidates}
        meta_scores: Dict[str, float] = {k: 0.0 for k in alive}
        title_hits: Dict[str, int] = {k: 0 for k in alive}
        # Long words first: they narrow the field for LIKE scans of short ones.
        folded = {
            key: (
                fold(s.get("title") or ""),
                fold(space_of(s)) + "\n" + fold(s.get("project") or ""),
                fold(s.get("branch") or ""),
                fold(_short_cwd(s.get("cwd") or "")),
                fold(AGENTS.get(s["agent"], s.get("agent_name") or s["agent"])) + "\n" + fold(s["agent"]),
                fold(s.get("first_prompt") or ""),
                fold(s.get("session_id") or ""),
            )
            for key, s in alive.items()
        }
        for term in sorted(q.terms, key=len, reverse=True):
            hits = searcher.message_hits(term, alive.keys() if len(term) < 3 else None)
            msg_hits[term] = hits
            survivors = {}
            for key, s in alive.items():
                title, space, branch, cwd, agent_name, prompt, sid = folded[key]
                gained = 0.0
                if term in title:
                    gained += W_TITLE
                    title_hits[key] += 1
                if term in space:
                    gained += W_SPACE
                if term in branch:
                    gained += W_BRANCH
                if term in cwd:
                    gained += W_CWD
                if term in agent_name:
                    gained += W_AGENT
                if term in prompt:
                    gained += W_PROMPT
                if sid and len(term) >= 6 and sid.startswith(term):
                    gained += W_TITLE
                hit = hits.get(key)
                if hit:
                    gained += 1.5 * math.sqrt(min(hit.count, 25))
                if gained > 0:
                    meta_scores[key] += gained
                    survivors[key] = s
            alive = survivors
            if not alive:
                break
        for key, s in alive.items():
            score = meta_scores[key]
            if title_hits[key] == len(q.terms):
                score += 8.0
                if fold(s.get("title") or "").strip() == " ".join(q.terms):
                    score += 6.0
            age_days = max(0.0, (now - _num(s.get("updated_at"))) / 86400.0)
            score += 3.0 * math.exp(-age_days / 14.0)
            if s.get("running"):
                score += 1.0
            s["score"] = round(score, 3)
            scored.append((score, s))
        results = [s for _, s in scored]
    else:
        results = candidates
        for s in results:
            s["score"] = 0.0

    if order == "relevance" and q.terms:
        results.sort(key=lambda s: (s["score"], _num(s.get("updated_at"))), reverse=True)
    elif order == "created":
        results.sort(key=lambda s: _num(s.get("created_at")), reverse=True)
    elif order == "oldest":
        results.sort(key=lambda s: _num(s.get("updated_at")))
    else:
        results.sort(key=lambda s: (_num(s.get("updated_at")), bool(s.get("running"))), reverse=True)

    total = len(results)
    page = results[: max(0, limit)]
    out = [decorate(s, q.terms, searcher, msg_hits) for s in page]

    projects: Dict[str, int] = {}
    for s in rows:
        name = space_of(s) or s.get("project") or ""
        if name:
            projects[name] = projects.get(name, 0) + 1
    facets = {
        "projects": sorted(projects.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:40],
        "running": sum(1 for s in rows if s.get("running")),
    }
    return {
        "ok": True,
        "query": q.as_dict(),
        "sort": order,
        "total": total,
        "results": out,
        "facets": facets,
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
    }


# Why a session can't be resumed: (code, English text). The mod shows its own translation of the code.
WHY_NOT = {
    "unknown_agent": "No resume command is known for this agent",
    "subagent": "A sub-agent transcript can't be resumed on its own",
    "archived": "Archived in Codex. Unarchive it in Codex, then resume.",
    "no_cwd": "No working folder is recorded, so it can't be resumed",
    "missing_cwd": "The working folder is gone: {detail}",
    "history_deleted": "The session's history file was deleted",
}
NOT_FOUND = "This session isn't in the index anymore. Its history may have been deleted."


def resume_info(s: dict) -> Tuple[bool, str, str]:
    """(resumable, code, detail). code is "" when it can be resumed."""
    if s.get("kind") == "live":
        return False, "", ""
    if s["agent"] not in AGENTS:
        return False, "unknown_agent", ""
    if s.get("is_subagent"):
        return False, "subagent", ""
    if s.get("archived"):
        return False, "archived", ""
    cwd = s.get("cwd") or ""
    if not cwd:
        return False, "no_cwd", ""
    if not os.path.isdir(cwd):
        return False, "missing_cwd", cwd
    if s.get("source_path") and not os.path.exists(s["source_path"]):
        return False, "history_deleted", ""
    return True, "", ""


def why_not_fields(s: dict) -> dict:
    resumable, code, detail = resume_info(s)
    text = WHY_NOT.get(code, "").replace("{detail}", detail)
    return {"resumable": resumable, "why_not": text, "why_not_code": code, "why_not_detail": detail}


def resume_args(s: dict) -> List[str]:
    if s["agent"] == "claude":
        return ["--resume", s["session_id"]]
    if s["agent"] == "codex":
        return ["resume", s["session_id"], "-C", s.get("cwd") or "."]
    return []


def decorate(s: dict, terms: Sequence[str], searcher: Searcher, msg_hits: Dict[str, Dict[str, Hit]]) -> dict:
    title = s.get("title") or (s.get("first_prompt") or "")[:80] or s.get("session_id") or "(untitled)"
    snippet_segs = None
    snippet_role = None
    snippet_id = None
    match = None
    if terms:
        in_title = any(t in fold(title) for t in terms)
        has_body = any(s["key"] in msg_hits.get(t, {}) for t in terms)
        if has_body and s.get("kind") != "live":
            row = searcher.best_message(s["key"], terms)
            if row is not None:
                snippet_segs = snippet(row["text"], terms)
                snippet_role = row["role"]
                snippet_id = row["id"]
        match = "title" if in_title else ("body" if snippet_segs else "meta")
    why = why_not_fields(s)
    running = s.get("running")
    return {
        "key": s["key"],
        "kind": s.get("kind") or "session",
        "agent": s["agent"],
        "agent_name": AGENTS.get(s["agent"], s.get("agent_name") or s["agent"]),
        "session_id": s.get("session_id") or "",
        "title": title,
        "title_segments": highlight(title, terms) if terms else [[title, False]],
        "title_source": s.get("title_source") or "",
        "project": s.get("project") or "",
        "space_name": space_of(s),
        "cwd": s.get("cwd") or "",
        "branch": s.get("branch") or "",
        "created_at": _num(s.get("created_at")),
        "updated_at": _num(s.get("updated_at")),
        "messages": int(s.get("message_count") or 0),
        "archived": bool(s.get("archived")),
        "origin": s.get("origin") or "",
        "running": running,
        "last_space_id": s.get("seen_space_id") or "",
        "match": match,
        "title_has_all": bool(terms) and all(t in fold(title) for t in terms),
        "snippet": {"segments": snippet_segs, "role": snippet_role, "message_id": snippet_id} if snippet_segs else None,
        "score": s.get("score", 0.0),
        **why,
        "resume_args": resume_args(s) if why["resumable"] else [],
    }


def preview(conn: sqlite3.Connection, key: str, text: str = "", message_id: Optional[int] = None, before: int = 4, after: int = 8) -> dict:
    q = parse_query(text)
    row = conn.execute("SELECT * FROM sessions WHERE key=?", (key,)).fetchone()
    if row is None:
        return {"ok": False, "error": "not_found", "message": NOT_FOUND}
    s = dict(row)
    searcher = Searcher(conn)
    focus_id = message_id
    if focus_id is None and q.terms:
        best = searcher.best_message(key, q.terms)
        focus_id = best["id"] if best is not None else None
    ids = [r[0] for r in conn.execute("SELECT id FROM messages WHERE sid=? ORDER BY id", (s["id"],))]
    if focus_id is not None and focus_id in ids:
        at = ids.index(focus_id)
        chosen = ids[max(0, at - before): at + after + 1]
    else:
        chosen = ids[-(before + after):]
        focus_id = None
    messages = []
    if chosen:
        marks = ",".join("?" * len(chosen))
        texts = store.message_texts(conn, chosen)
        for m in conn.execute(f"SELECT id, role, ts FROM messages WHERE id IN ({marks}) ORDER BY id", chosen):
            text = texts.get(m["id"], "")
            body = excerpt(text, q.terms) if m["id"] == focus_id else excerpt(text, [])
            messages.append({
                "id": m["id"], "role": m["role"], "ts": m["ts"], "text": body,
                "segments": highlight(body, q.terms) if q.terms else [[body, False]],
                "match": m["id"] == focus_id,
            })
    why = why_not_fields(s)
    return {
        "ok": True,
        "key": key,
        "agent": s["agent"],
        "agent_name": AGENTS.get(s["agent"], s["agent"]),
        "session_id": s["session_id"],
        "title": s["title"],
        "cwd": s["cwd"],
        "branch": s["branch"],
        "created_at": s["created_at"],
        "updated_at": s["updated_at"],
        "message_count": len(ids),
        "first_index": ids.index(chosen[0]) if chosen else 0,
        "messages": messages,
        "focus_id": focus_id,
        "source_path": s["source_path"],
        **why,
        "resume_args": resume_args(s) if why["resumable"] else [],
    }


def check(conn: sqlite3.Connection, key: str) -> dict:
    row = conn.execute("SELECT * FROM sessions WHERE key=?", (key,)).fetchone()
    if row is None:
        return {"ok": False, "error": "not_found", "message": NOT_FOUND}
    s = dict(row)
    why = why_not_fields(s)
    return {
        "ok": True, "key": key, "agent": s["agent"], "session_id": s["session_id"], "cwd": s["cwd"],
        "source_exists": os.path.exists(s["source_path"]), "cwd_exists": bool(s["cwd"]) and os.path.isdir(s["cwd"]),
        **why, "resume_args": resume_args(s) if why["resumable"] else [],
    }
