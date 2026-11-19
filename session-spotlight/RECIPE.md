# Session Spotlight

Cmd+K opens a centered search dialog over every Claude Code and Codex session on this computer, running or ended. Type to search titles, what was said, projects and folders; the list shows the running ones first, then recent ones. Enter goes to the exact terminal that runs a session, or resumes an ended one in its own folder. Everything is indexed locally by a small Python program that ships inside the mod.

![Session Spotlight](preview.png)

## What you see

- A dialog (`kind: "dialog"`, 920×640 px, Herdr's own frame), the window dimmed behind it. Nothing is added to the layout.
- **Search bar, 56px:** an 18px search glyph in `dim`, a borderless 16px field ("Search sessions, conversations, projects…", drawn by the view behind a transparent input so it follows the language), a 14px spinner while a search, the index or a resume is running, and an `esc` cap.
- **Filter chips, 40px:** five chips, each a 13px glyph, a 12px label and a chevron: date ("Any time"), project or Space ("All projects"), agent ("All agents"), status ("Any status"), sort ("Sort"). A chip whose filter is set is `accent` on an 10% accent tint. "Clear filters" at the right when any is set. A chip opens a dropdown under it (a `Popup` anchored `top_left`): 30px rows, a check on the current value, project rows with their session count.
- A 1px `border` line, then the body, a 1px line and a 34px footer with key caps (`↑↓ Select`, `↵ Go to|Resume|Open`, `⇥ Filters`, `esc Close`) and, at the right, "N sessions · Nms", or an error in `blocked`, or a resume warning.
- **Body, left: the results**, 48% of the width (360–500px), a `v_virtual_list`:
  - With nothing typed and the recent sort: an "Open sessions N" section (sessions whose agent is alive in a Herdr terminal), then "Recent sessions N" (30px headers, 11px semibold `dim`).
  - Rows 58px (78px with a snippet), 6px in, 9px radius. Line 1: the agent's icon (20px: `icons/claude.svg`, `icons/codex.svg`, else a terminal glyph on `hover`), the title at 13.5px with matched words in `accent` semibold, and for an open session a pill from Herdr's agent status: working = spinner + "Working" in `working`, blocked = "Needs input" in `blocked`, done = "Done" in `done`, idle or no status = a quiet gray "Idle" (dot in `idle`, text `muted`, on `hover`). Never a "running" look for an idle agent. Archived Codex sessions say "Archived". Line 2 (12px `dim`): `Space or project · agent · Today 14:32`. Line 3 only when the words matched the conversation and not all of them are in the title: "You" or "AI" then a one-line snippet starting just before the first match, matches in `accent`.
  - Selected row on `selected`, hovered on `hover`.
- **Body, right: the preview** (hidden below 700px width): the icon (26px) and the title (15.5px semibold, two lines max), status pill and agent; a meta grid (Project/Space, Folder in the terminal font, Branch, Started, Last active with a relative time, Messages, Session ID); a 32px action bar on an accent tint saying exactly what Enter does ("↵ Go to its open terminal · space › tab (t12)", "↵ Resume in a new tab · claude --resume 1a2b3c4d…", or "Can't resume · why" in `blocked`); then "Matching conversation" / "Recent conversation" with the message range, and the messages in a scroll area that opens on the matched one: the person's on `hover` headed "You", the agent's headed by its name in `accent`, the matched one outlined in `accent` with matching words on a 25% accent tint.
- **Language:** English by default; `"language": "ko"` (or `"auto"`) in `~/.config/herdr-session-spotlight/config.json` switches every string, date and relative time (`i18n.js`).
- Empty states are centered in `dim`: loading, first indexing, "No sessions match “…”", or no session for the filters, with a "Clear filters" button when filters are on.

## How it behaves

- Opening shows the last list at once (kept in module scope), focuses the field, then in parallel: maps running terminals to sessions (`resolve`), updates the index incrementally (`index`), and searches. Typing searches 60 ms after the last key; only the newest answer is used. Running terminals are re-checked every 4 s while open.
- ↑/↓ and PageUp/PageDown move the selection (headers are skipped, the list scrolls only as far as needed). Click selects; clicking the selected row opens it. Tab / Shift+Tab walk the chip menus; in a menu ↑/↓ choose, Enter applies, ←/→ move to the next chip, Esc closes the menu. Esc closes the dialog.
- Typed operators narrow further and show in their chip: `project:` (substring of the project or Space name), `agent:claude|codex|other`, `after:` / `before:` (`YYYY-MM-DD`, `today`, `7d`, `2w`), `status:running|ended`, `sort:recent|created|relevance|oldest`. "Custom range…" in the date menu writes `after:<a week ago> before:<today>` into the field with the first date selected.
- **Enter always asks again** where the session runs (`resolve` on the current terminals) and decides with `decideOpen()` (lib.js). It starts nothing, and shows why in the footer, when that answer failed, when a terminal it asked about is missing from it, when a terminal of the same agent couldn't be identified, or when the terminal holding the session can't be focused.
- **A terminal holds the session:** `space.select`, `tab.select`, `pane.focus {terminal}` with that exact address (the list's address may be stale); a sub-agent without a pane gets `agent.focus`, anything else `terminal.peek`. Nothing is started.
- **No terminal holds it:** the engine checks the history file and folder still exist (else a warning, and the index is refreshed); if the terminals changed while checking, it stops. Otherwise the agent's launcher from `knownAgents()` (programs.json `run`) plus `--resume <id>` (Claude) or `resume <id> -C <folder>` (Codex) starts in a new tab named after the session, in the Space it was last seen in, else a Space on its folder, else a new Space on that folder. The same session can't be started twice within 15 s. A toast confirms.

## Built from

- **One mod**, `mods/session-spotlight/`: `main.js` (the View), `lib.js` (pure helpers, tested with node), `i18n.js` (en, ko strings), `mod.json` (`place: "none"`, `overlay: {kind: "dialog", width: 920, height: 640}`), `icons/*.svg`, and `engine/` (Python 3.9+ standard library).
- **A `keys.json` snippet**: `"global": {"cmd-k": "mod.open:session-spotlight"}`. (Not Cmd+Shift+K: the Notion desktop app takes that one system-wide, so it never reaches Herdr.)
- **Herdr functions:** `exec`, `knownAgents`, `terminals`, `agents`, `panes`, `spaces`, `run`, `notify`, `theme`, `settings`, `props`, `closeOverlay`, `appHome`, `checking`, `nextCommand`.
- **Commands:** `space.select`, `tab.select`, `pane.focus`, `agent.focus`, `terminal.peek`, `tab.new {space, folder, argv, name}`, `space.new {folder, argv, tab}`.
- **The engine**, run as `python3 -B -I -S engine/spotlight.py <command>`, prints one JSON object:
  - `index`: incremental. Each history file's size, mtime, byte offset and parser state are kept; unchanged files are skipped, grown files are read from the offset, shrunk or rewritten ones re-read, deleted ones dropped. One indexer at a time (`flock`).
  - `search --query --agent --project --since --status --sort --limit --live <json>`: results with `title_segments`, `snippet.segments` (`[text, matched]` pairs, so JS never maps offsets), `running`, `resumable`, `why_not`, `resume_args`, and `facets.projects`.
  - `resolve --terminals <json>`: terminal address → session id by process: Claude `~/.claude/sessions/<pid>.json` whose `procStart` equals `ps -o lstart` in the C locale and UTC; Codex by `lsof` on the open `rollout-*.jsonl`; else `--resume <uuid>` in argv. Also records the Space each session ran in (`herdr_seen`).
  - `preview --key --query --message`, `check --key`, `stats`, `reset --yes`, `doctor`, `init-config`.
- **Index:** `~/.local/share/herdr-session-spotlight/index.sqlite3` (0600): `sessions` (one per agent session, integer id), `messages` (id, session id, role, time — narrow on purpose), `messages_fts` (FTS5 `trigram`, the text), `sources`, `herdr_seen`, `meta`. Words of 3+ characters use the FTS index; shorter ones scan.
- **What is indexed:** user and assistant text only. Tool calls and results, thinking, attachments, meta/compact records, sidechains and injected instruction blocks are skipped; secrets are masked before storage, titles included.

## Watch out

- `herdr-app check` runs `init()`: the mod returns early under `checking()`.
- Never write into the mod folder at run time: a saved file there reloads the mod. The engine runs with `-B` (no `__pycache__`), and the index lives under `~/.local/share`.
- `v_virtual_list` rows can't have handlers: use `on_item_click(key)` on the list. Rows need fixed heights (`items.map(itemHeight)`).
- An absolutely positioned dropdown inside the dialog didn't paint; `Popup.new(id, trigger).anchor("top_left").content(...)` paints in a layer above.
- `Tab` is bound by the app; `cx.bind_keys([{keystroke: "tab", action, context}])` with the root's `.key_context(context).on_action(action, …)` wins.
- `on_size_change` reports window pixels: divide by `settings().zoom`.
- Claude writes `procStart` in UTC and the C locale; run `ps` with `TZ=UTC LC_ALL=C` or the comparison never matches on a non-English system.
- Claude records' `cwd` follows the shell's `cd` during a session: the first one is where the session started and where it must resume.
- A sub-agent's `herdr.space`/`herdr.tab` labels can name another space; place it by its parent's pane.
- Decide a terminal's agent by program name (argv[0], or what a launcher shell runs), never by substring: `-C /private/tmp/claude-501/…` is not Claude.
- A trust dialog in a new folder belongs to the agent; the mod doesn't answer it.
- `herdr-app do session-spotlight.<command>` reaches the open dialog only; command names can't carry `:value`, so scripted checks hex-encode (`query-<hex>`).

## Done when

- `herdr-app check mods/session-spotlight` passes; `python3 -B -m unittest discover -s tests/engine` and `node --test tests/mod/*.test.mjs` pass.
- Cmd+K opens the dialog with the field focused; Esc closes it.
- With nothing typed, running sessions come first, then sessions by last activity, each with project · agent · time.
- A word from a session's title lists it first; a word only said in a conversation lists it with a highlighted snippet, and the preview opens on that message.
- `agent:codex`, a date chip, the project chip and each sort change the list as named.
- Enter on a running session focuses its exact terminal, also when two Spaces share a name; the terminal count doesn't change.
- Enter on an ended Claude/Codex session starts `claude --resume <id>` / `codex resume <id> -C <folder>` in its folder; the new terminal maps back to the same session id.
- Enter on a session whose history file was deleted shows a warning and starts nothing.
