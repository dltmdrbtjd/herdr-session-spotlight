# Session Spotlight — research and design

**English** · [한국어](DESIGN.ko.md)

## 1. The Herdr environment (herdr-app 0.1.16 / hc 0.1.21)

Sources: `~/.config/herdr-app/AGENTS.md`, `herdr.d.ts` and `gpui-kit.d.ts` (rewritten by the app on every start,
so they are the truth for that version), `herdr-app commands`, and probes run inside the live app.

| Need | Official API used | How it was confirmed |
|---|---|---|
| Spaces / tabs / terminals / agents | `spaces()`, `panes()`, `agents()`, `terminals()` | a throwaway probe mod dumped real values (`terminals()` carries `foreground.pid/argv`, `parent`, `labels`, `program`) |
| Focus | `space.select {id}`, `tab.select {id}`, `pane.focus {terminal}`, `agent.focus {terminal}`, `terminal.peek` | `herdr-app commands` argument lists, end-to-end runs in the app |
| Start in a new tab / Space | `tab.new {space, folder, argv, name}`, `space.new {folder, argv, tab}` | same |
| The dialog | `mod.json` `overlay: {kind: "dialog", width, height}` + `mod.open` (toggles), `closeOverlay(props().overlay)` | shipped `picker`, `machine-add` |
| Dropdowns | gpui-kit `Popup.new(id, trigger).anchor(...).content(...)` | an `absolute()` panel inside the dialog never painted |
| Shortcut | `keys.json` `global`: `"cmd-k": "mod.open:session-spotlight"` | no clash in Herdr's keys, loaded per `keys()`. The first choice, `cmd-shift-k`, is taken system-wide by the Notion desktop app (found by the user) |
| Tab key | `cx.bind_keys([{keystroke: "tab", action, context}])` + the root's `key_context` / `on_action` | the app binds Tab to focus movement |
| Programs | `exec(cmd, args, {timeout})` (the user's environment, an argument array, no shell) | probe: PATH, `python3` |
| Checking a mod | `herdr-app check <folder>`, `herdr-app status` (errors), `herdr-app shot` | after every change |
| Driving the dialog from scripts | `herdr-app do <mod>.<command>` → `nextCommand()` (only while open; no `:value`) | `scripts/drive.sh` |
| Language | `readTextFile` of the config, `exec("defaults", ["read", "-g", "AppleLocale"])` for `auto` | — |

**Mod runtime limits:** no DOM, Node APIs or `setTimeout`; no SQLite; writes only under `~/.config/herdr-app`
(`fs/promises`); `readTextFile` up to 1 MiB. So the SQLite FTS5 index lives in a **small local engine process
shipped inside the mod folder (Python standard library)**: no network, no extra packages, no daemon. The mod
runs the command it needs through `exec` while it's open.

## 2. Prior art: herdr-omnisearch (MIT)

`dmnkf/herdr-omnisearch` (v0.17) was read for ideas only. No code was copied.

| Area | OmniSearch | Session Spotlight |
|---|---|---|
| Shape | Herdr TUI plugin + a popup mod for the app, a separate CLI installed with `uv tool install` | one mod with its engine inside, installed by copying |
| Scope | live screen text + a session archive (off by default), TUI and remote machines | Claude/Codex session history + Herdr's open terminals, this computer only |
| Index | several SQLite files (live/app/archive), a periodic watcher | one SQLite file: incremental (byte offsets, fingerprints) + FTS5 trigram |
| Which session runs where | Claude pid files (and parent pid), a session id in the command line | Claude pid files **checked against the process start time**, Codex **open rollout file (lsof)**, argv fallback |
| UX | a 92%×88% popup, Live/Sessions modes, screen preview | a centered 920×640 dialog, one list (open / recent), filter chips and operators, conversation preview |

Ideas taken: the list of blocks agents inject into the user's turn, finding a running Claude session through
`sessions/<pid>.json`, and gpui tips (popup sizing, zoom, the Tab binding). The license is MIT; ideas carry no
obligation and no code was copied, but the README credits it.

## 3. Agent history formats (checked locally)

**Claude Code 2.1.283** — `~/.claude/projects/<cwd with / → ->/<sessionId>.jsonl`
- `user` / `assistant` records: `message.content` is a string or `[{type: text|tool_use|tool_result|thinking|image}]`;
  flags `isMeta`, `isCompactSummary`, `isVisibleInTranscriptOnly`, `isSidechain`.
- Title: `custom-title` (renamed by the user) > `ai-title` > `summary` > `agent-name` > first prompt.
- `cwd` follows the shell's `cd` during a session, so the **first** `cwd` is where it started and where it must resume.
- `~/.claude/sessions/<pid>.json`: `{pid, sessionId, cwd, procStart: "Thu Nov 19 06:18:43 2026" (UTC, C locale), startedAt, status, …}`;
  not written before the folder is trusted.
- Sub-agents: `<sessionId>/subagents/agent-*.jsonl` (not resumable on their own → skipped by default).
- Resume: `claude --resume <sessionId>`, from that folder.

**Codex CLI 0.169.1** — `~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl`, `archived_sessions/*.jsonl(.zst)`
- `session_meta.payload`: `id, cwd, timestamp, source (cli|vscode|exec|{subagent}), cli_version, git`.
- `response_item` `type: message`, `role: developer|user|assistant`, `content[].type: input_text|output_text`;
  user turns also carry `AGENTS.md` instructions and `<environment_context>`.
- Names: `session_index.jsonl` `{id, thread_name}` (renaming doesn't touch the rollout → re-read on every index run).
- A running codex keeps its rollout open → `lsof` names it (sub-agent threads may be open too).
- Resume: `codex resume <id> -C <dir>` (after Herdr's launcher, `codex --no-daemon`).

## 4. Architecture

```text
Session Spotlight
├── Spotlight UI .................. main.js (gpui-kit View, dialog overlay), i18n.js (en, ko)
├── Session Navigation ............ lib.js decideOpen / planFocus / resumeSpace / resumeArgv
├── Session Search Service ........ engine/search.py   (spotlight.py search | preview | check)
├── Session Adapters
│   ├── Herdr Live Sessions ....... lib.js liveTerminals + engine/live.py (spotlight.py resolve)
│   ├── Claude History ............ engine/adapters.py ClaudeAdapter
│   └── Codex History ............. engine/adapters.py CodexAdapter
└── Local Search Index ............ engine/store.py + indexer.py (spotlight.py index)
```

The UI ↔ engine boundary is one JSON object per command. Highlights travel as `[text, matched]` segments, so
Python code-point offsets never have to be mapped onto JavaScript's UTF-16. The engine's user-facing reasons come
with a code (`why_not_code`, `error`) that the mod translates.

### Data model

| Table | Contents |
|---|---|
| `sessions` | integer `id`, `key` (`machine|agent|session id`, unique), title and its source, cwd / project / branch, created / last active, message count, first / last prompt, sub-agent and archived flags, source file |
| `messages` | `id, sid, role, ts` — narrow on purpose: mapping FTS hits to sessions reads this table, and small rows made it 2.3× faster |
| `messages_fts` | FTS5 `trigram`, the text (rowid = messages.id) |
| `sources` | per history file: `size, mtime_ns, offset, state (JSON)` for incremental indexing |
| `herdr_seen` | the Herdr Space / tab / address a session last ran in — for the project filter and where to resume (the one thing logs can't give back, so kept across schema changes) |
| `meta` | schema version, settings hash, last indexed, progress |

Identifiers: sessions by machine + agent + session id; terminals by herdr-core address (`t3n`, `machine/t3`
remotely); Spaces and tabs by Herdr id. **A running terminal is never linked to history by title or project name.**

### Incremental indexing

Same `(size, mtime)` → skipped · **grew**, same inode, the first 4 KiB and the 256 bytes before the stored offset
unchanged, and this file owns the session → parsed from the stored offset (an unfinished last line waits for the
next run) · any other change (an equal-sized rewrite, a replacement, a truncation, another session id) → that
session is read again from the start · file deleted → only the session **it owns** goes, and another copy of the
same session (e.g. in `archived_sessions`) takes its place · excluded paths or options changed → the settings hash
changes and everything is rebuilt · new schema version → tables are recreated. One indexer runs at a time
(`flock`), and `reset` deletes under the same lock.

### Search and scoring

Per word: title 10 · Space / project 6 · first prompt 3 · branch 3 · folder (below home) 2 · agent 2 · messages
`1.5 × √min(matching messages, 25)`. Every word must match somewhere (AND); +8 when the title holds every word,
+6 when it equals the query, recency `3·e^(−days/14)`, +1 when open. Words of 3+ characters use the FTS trigram
index; shorter ones are scanned within the sessions still in play.

## 5. Performance (measured; details in VERIFICATION.md)

| Data | First index | Nothing changed | Search (engine) | Search (the whole process the mod runs) |
|---|---|---|---|---|
| Real history, 212 sessions / 7k messages | 2.4–3.0 s | 6 ms | 1–26 ms | about 30–60 ms |
| Synthetic, 1,000 sessions / 40k messages | 2.1 s | 10 ms | 5–56 ms | median 88–97 ms |
| Synthetic, 3,000 sessions / 180k messages | 10.3 s | 27 ms | 17–217 ms | median 255 ms |

The synthetic data uses about 20 words, so nearly every word appears in every session: a worst case. The 100 ms
goal holds up to 1,000 sessions; multi-word searches over 3,000 sessions / 180k messages exceed it. Typing is
debounced (60 ms), only the newest answer is applied, and `exec` is asynchronous, so the UI never blocks.

## 6. Not implemented, and why

- Jumping to a past message: Claude Code and Codex have no such option → the preview scrolls to the match.
- Searching remote machines: needs the engine on each machine, `exec({on})` and an explicit opt-in; there was no
  remote machine to verify it on.
- Herdr's finished terminals (herdr-core's finished list): they only carry a title and folder, and the agents'
  own history is more accurate.
