"""Where things live and what the person chose to leave out.

Index:   $XDG_DATA_HOME/herdr-session-spotlight/index.sqlite3  (~/.local/share/...)
Config:  $XDG_CONFIG_HOME/herdr-session-spotlight/config.json  (~/.config/...)

Both folders are created 0700 and the index file 0600. Nothing here ever
writes to Claude's or Codex's own folders; their logs are only read.
"""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import List, Optional

APP = "herdr-session-spotlight"

DEFAULTS = {
    # Session folders whose cwd matches one of these globs are never indexed
    # (and are dropped from the index when added later). `~` is expanded.
    "exclude_paths": [],
    # Agents to index. Known: "claude", "codex".
    "agents": ["claude", "codex"],
    # Index the agent's answers too, not only what the person typed.
    "index_assistant": True,
    # Claude Code's sub-agent transcripts (not resumable on their own).
    "include_subagents": False,
    # Codex sessions moved to archived_sessions/ (read through zstd when available).
    "include_archived": True,
    # Characters kept per message in the index.
    "max_message_chars": 6000,
    # Override the agents' history folders (defaults follow CLAUDE_CONFIG_DIR / CODEX_HOME).
    "claude_home": None,
    "codex_home": None,
    # The mod's UI language: "en" (default), "ko", or "auto" (the system's, English otherwise).
    "language": "en",
}


def _xdg(var: str, fallback: str) -> Path:
    value = os.environ.get(var)
    return Path(value).expanduser() if value else Path.home() / fallback


def data_dir() -> Path:
    override = os.environ.get("SPOTLIGHT_DATA_DIR")
    return Path(override).expanduser() if override else _xdg("XDG_DATA_HOME", ".local/share") / APP


def config_path() -> Path:
    override = os.environ.get("SPOTLIGHT_CONFIG")
    return Path(override).expanduser() if override else _xdg("XDG_CONFIG_HOME", ".config") / APP / "config.json"


def ensure_private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


class Config:
    """The person's choices, defaults from DEFAULTS (a plain class: dataclasses cost import time)."""

    def __init__(self) -> None:
        self.exclude_paths: List[str] = []
        self.agents: List[str] = ["claude", "codex"]
        self.index_assistant: bool = True
        self.include_subagents: bool = False
        self.include_archived: bool = True
        self.max_message_chars: int = 6000
        self.claude_home: Optional[str] = None
        self.codex_home: Optional[str] = None
        self.language: str = "en"
        self.errors: List[str] = []

    @property
    def claude_root(self) -> Path:
        base = self.claude_home or os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
        return Path(base).expanduser()

    @property
    def codex_root(self) -> Path:
        base = self.codex_home or os.environ.get("CODEX_HOME") or "~/.codex"
        return Path(base).expanduser()

    def excluded(self, cwd: Optional[str]) -> bool:
        if not cwd or not self.exclude_paths:
            return False
        for pattern in self.exclude_paths:
            pat = os.path.expanduser(pattern).rstrip("/")
            if fnmatch.fnmatch(cwd, pat) or cwd == pat or cwd.startswith(pat + "/"):
                return True
        return False


def load_config() -> Config:
    cfg = Config()
    path = config_path()
    if not path.exists():
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        cfg.errors.append(f"config ignored ({path}): {exc}")
        return cfg
    if not isinstance(raw, dict):
        cfg.errors.append(f"config ignored ({path}): not an object")
        return cfg
    for key, default in DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        if default is not None and not isinstance(value, type(default)):
            cfg.errors.append(f"config key {key!r} ignored: expected {type(default).__name__}")
            continue
        setattr(cfg, key, value)
    return cfg


def write_default_config() -> Path:
    path = config_path()
    if path.exists():
        return path
    ensure_private_dir(path.parent)
    body = {k: v for k, v in DEFAULTS.items() if v is not None}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def resolve_language(cfg: "Config") -> str:
    """The UI language the mod should use: "en" or "ko". "auto" follows macOS's AppleLocale."""
    want = (cfg.language if isinstance(cfg.language, str) else "en").strip().lower()
    if want in ("en", "ko"):
        return want
    if want == "auto":
        import subprocess

        try:
            out = subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        return "ko" if out.strip().lower().startswith("ko") else "en"
    return "en"
