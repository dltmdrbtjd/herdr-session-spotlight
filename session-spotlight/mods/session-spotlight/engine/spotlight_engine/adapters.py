"""Session adapters: read Claude Code and Codex history files, read-only.

Each adapter turns one history file into session metadata plus the
conversation's user/assistant text. Tool calls, tool output, thinking,
attachments, environment and instruction blocks are left out on purpose:
they are where file contents, environment variables and tokens live.

Files are read as JSON Lines from a byte offset, so a growing transcript is
re-read only from where the last run stopped (see indexer.py).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from .textutil import title_from_prompt

MAX_RECORD_BYTES = 2 * 1024 * 1024

Emit = Callable[[str, float, str], None]

# Text that agents inject into the user turn: instructions, environment,
# command echoes and tool plumbing. Never what the person asked.
NOISE_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<apps_instructions>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<INSTRUCTIONS>",
    "<user_instructions>",
    "[Request interrupted by user",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<user_shell_command>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<task-notification>",
    "<system-reminder>",
    "<subagent_notification>",
    "<turn_aborted>",
    "<goal_context>",
    "<thinking>",
    "<skill>",
    "<recommended_plugins>",
    "[external_agent_tool",
    "<external_agent_tool",
    "Caveat: The messages below were generated",
    "The following is the Codex agent history",
    "The following skills are available",
    "This session is being continued from a previous conversation",
)


def is_noise(text: str) -> bool:
    stripped = (text or "").lstrip()
    if not stripped:
        return True
    if stripped.startswith(NOISE_PREFIXES):
        return True
    if stripped.startswith("{") and stripped.rstrip().endswith("}"):
        try:
            value = json.loads(stripped)
        except ValueError:
            value = None
        if isinstance(value, dict) and "outcome" in value and set(value) <= {"outcome", "risk_level", "rationale", "user_authorization"}:
            return True
    if len(stripped) > 12000 and ("You are Codex" in stripped or "AGENTS.md" in stripped):
        return True
    return False


def iso_epoch(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e12 else v
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def message_text(content) -> str:
    """User/assistant text only: tool_use, tool_result, thinking and images are skipped."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") in ("text", "input_text", "output_text"):
            parts.append(item.get("text") or "")
    return "\n".join(p for p in parts if p)


def read_records(path: Path, offset: int = 0) -> Iterator[Tuple[dict, int]]:
    """(record, offset after it). Stops before an unfinished last line."""
    with path.open("rb") as handle:
        handle.seek(offset)
        position = offset
        while True:
            line = handle.readline(MAX_RECORD_BYTES + 1)
            if not line:
                return
            if not line.endswith(b"\n"):
                if len(line) <= MAX_RECORD_BYTES:
                    return  # still being written: pick it up next run
                # Oversized record: skip to its end.
                while line and not line.endswith(b"\n"):
                    position += len(line)
                    line = handle.readline(MAX_RECORD_BYTES + 1)
                position += len(line)
                continue
            position += len(line)
            if len(line) > MAX_RECORD_BYTES:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                yield item, position


def read_zst_records(path: Path) -> Iterator[Tuple[dict, int]]:
    try:
        from compression import zstd  # Python 3.14+
    except ImportError:
        return
    try:
        with zstd.open(path, "rb") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    yield item, 0
    except (OSError, zstd.ZstdError):  # type: ignore[attr-defined]
        return


class Adapter:
    agent = ""

    def discover(self, cfg) -> List[Path]:
        raise NotImplementedError

    def new_state(self, path: Path) -> dict:
        raise NotImplementedError

    def feed(self, state: dict, record: dict, emit: Emit) -> None:
        raise NotImplementedError

    def meta(self, state: dict, path: Path) -> Optional[dict]:
        raise NotImplementedError

    def records(self, path: Path, offset: int) -> Iterator[Tuple[dict, int]]:
        if path.name.endswith(".zst"):
            return read_zst_records(path) if offset == 0 else iter(())
        return read_records(path, offset)

    def appendable(self, path: Path) -> bool:
        return not path.name.endswith(".zst")


def _touch(state: dict, ts: float) -> None:
    if ts:
        if not state.get("created") or ts < state["created"]:
            state["created"] = ts
        if ts > state.get("updated", 0):
            state["updated"] = ts


def _prompt(state: dict, text: str) -> None:
    if not state.get("first_prompt"):
        state["first_prompt"] = text[:400]
    state["last_prompt"] = text[:400]


class ClaudeAdapter(Adapter):
    """~/.claude/projects/<folder>/<session-id>.jsonl"""

    agent = "claude"

    def discover(self, cfg) -> List[Path]:
        root = cfg.claude_root / "projects"
        if not root.is_dir():
            return []
        found = sorted(root.glob("*/*.jsonl"))
        if cfg.include_subagents:
            found += sorted(root.glob("*/*/subagents/*.jsonl"))
        return found

    def new_state(self, path: Path) -> dict:
        return {
            "session_id": path.stem,
            "subagent": path.parent.name == "subagents",
            "msgs": 0,
        }

    def feed(self, state: dict, record: dict, emit: Emit) -> None:
        kind = record.get("type")
        if kind == "custom-title":
            state["title_custom"] = record.get("customTitle") or state.get("title_custom")
            return
        if kind == "ai-title":
            state["title_ai"] = record.get("aiTitle") or state.get("title_ai")
            return
        if kind == "agent-name":
            state["title_agent"] = record.get("agentName") or state.get("title_agent")
            return
        if kind == "summary":
            state["title_summary"] = record.get("summary") or state.get("title_summary")
            return
        if kind not in ("user", "assistant"):
            return
        if not state.get("subagent") and record.get("isSidechain"):
            return
        if record.get("isMeta") or record.get("isCompactSummary") or record.get("isVisibleInTranscriptOnly"):
            return
        if not state.get("session_id_seen") and record.get("sessionId"):
            state["session_id"] = record["sessionId"]
            state["session_id_seen"] = True
        # The first folder is where the session was started: Claude files its history under it and
        # resumes from it. Later records follow the shell's `cd`.
        if record.get("cwd") and not state.get("cwd"):
            state["cwd"] = record["cwd"]
        if record.get("gitBranch"):
            state["branch"] = record["gitBranch"]
        if record.get("version"):
            state["version"] = record["version"]
        ts = iso_epoch(record.get("timestamp"))
        _touch(state, ts)
        message = record.get("message") or {}
        role = message.get("role") or kind
        text = message_text(message.get("content"))
        if role not in ("user", "assistant") or is_noise(text):
            return
        if role == "user":
            _prompt(state, text)
        state["msgs"] = state.get("msgs", 0) + 1
        emit(role, ts, text)

    def meta(self, state: dict, path: Path) -> Optional[dict]:
        title, source = "", ""
        for key, label in (("title_custom", "custom"), ("title_ai", "ai"), ("title_summary", "summary"), ("title_agent", "name")):
            if state.get(key):
                title, source = state[key], label
                break
        if not title and state.get("first_prompt"):
            title, source = title_from_prompt(state["first_prompt"]), "prompt"
        if not state.get("msgs") and not title:
            return None
        return {
            "session_id": state.get("session_id") or path.stem,
            "title": title,
            "title_source": source,
            "cwd": state.get("cwd") or "",
            "branch": state.get("branch") or "",
            "created_at": state.get("created") or 0.0,
            "updated_at": state.get("updated") or 0.0,
            "first_prompt": state.get("first_prompt") or "",
            "last_prompt": state.get("last_prompt") or "",
            "is_subagent": bool(state.get("subagent")),
            "archived": False,
            "origin": "cli",
            "version": state.get("version") or "",
            "message_count": state.get("msgs", 0),
        }


_CODEX_ID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


class CodexAdapter(Adapter):
    """~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (+ archived_sessions/)."""

    agent = "codex"

    def __init__(self) -> None:
        self.thread_names: Dict[str, str] = {}

    def load_thread_names(self, cfg) -> None:
        self.thread_names = {}
        path = cfg.codex_root / "session_index.jsonl"
        if not path.is_file():
            return
        for item, _ in read_records(path):
            sid, name = item.get("id"), item.get("thread_name")
            if sid and name:
                self.thread_names[sid] = name

    def discover(self, cfg) -> List[Path]:
        root = cfg.codex_root
        found = sorted((root / "sessions").glob("**/rollout-*.jsonl")) if (root / "sessions").is_dir() else []
        if cfg.include_archived and (root / "archived_sessions").is_dir():
            found += sorted((root / "archived_sessions").glob("rollout-*.jsonl"))
            found += sorted((root / "archived_sessions").glob("rollout-*.jsonl.zst"))
        return found

    def new_state(self, path: Path) -> dict:
        match = _CODEX_ID.search(path.name)
        return {
            "session_id": match.group(1) if match else path.stem,
            "archived": "archived_sessions" in path.parts,
            "msgs": 0,
        }

    def feed(self, state: dict, record: dict, emit: Emit) -> None:
        kind = record.get("type")
        payload = record.get("payload") or {}
        if kind == "session_meta":
            state["session_id"] = payload.get("id") or state.get("session_id")
            state["cwd"] = payload.get("cwd") or state.get("cwd")
            state["version"] = payload.get("cli_version") or state.get("version")
            source = payload.get("source")
            if isinstance(source, dict) and "subagent" in source:
                state["subagent"] = True
            if payload.get("parent_thread_id"):
                state["subagent"] = True
            state["origin"] = source if isinstance(source, str) else ("subagent" if state.get("subagent") else "")
            git = payload.get("git") or {}
            if isinstance(git, dict) and git.get("branch"):
                state["branch"] = git["branch"]
            _touch(state, iso_epoch(payload.get("timestamp") or record.get("timestamp")))
            return
        if kind == "turn_context":
            if payload.get("cwd") and not state.get("cwd"):
                state["cwd"] = payload["cwd"]
            return
        if kind != "response_item" or payload.get("type") != "message":
            if record.get("timestamp") and kind == "event_msg":
                _touch(state, iso_epoch(record.get("timestamp")))
            return
        role = payload.get("role")
        if role not in ("user", "assistant"):
            return
        ts = iso_epoch(record.get("timestamp"))
        _touch(state, ts)
        text = message_text(payload.get("content"))
        if is_noise(text):
            return
        if role == "user":
            _prompt(state, text)
        state["msgs"] = state.get("msgs", 0) + 1
        emit(role, ts, text)

    def meta(self, state: dict, path: Path) -> Optional[dict]:
        sid = state.get("session_id") or path.stem
        title, source = self.thread_names.get(sid, ""), "name"
        if not title and state.get("first_prompt"):
            title, source = title_from_prompt(state["first_prompt"]), "prompt"
        if not title:
            source = ""
        if not state.get("msgs") and not title:
            return None
        return {
            "session_id": sid,
            "title": title,
            "title_source": source,
            "cwd": state.get("cwd") or "",
            "branch": state.get("branch") or "",
            "created_at": state.get("created") or 0.0,
            "updated_at": state.get("updated") or 0.0,
            "first_prompt": state.get("first_prompt") or "",
            "last_prompt": state.get("last_prompt") or "",
            "is_subagent": bool(state.get("subagent")),
            "archived": bool(state.get("archived")),
            "origin": state.get("origin") or "",
            "version": state.get("version") or "",
            "message_count": state.get("msgs", 0),
        }


def adapters_for(cfg) -> List[Adapter]:
    out: List[Adapter] = []
    for name in cfg.agents:
        if name == "claude":
            out.append(ClaudeAdapter())
        elif name == "codex":
            out.append(CodexAdapter())
    return out


def file_stamp(path: Path) -> Optional[Tuple[int, int]]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns
