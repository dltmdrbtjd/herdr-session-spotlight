# Session Spotlight

Cmd+Shift+K opens a centered search dialog over every Claude Code and Codex session on this computer, running or ended. Type to search titles, what was said, projects and folders; the list shows the running ones first, then recent ones. Enter goes to the exact terminal that runs a session, or resumes an ended one in its own folder. Everything is indexed locally by a small Python program that ships inside the mod.

![Session Spotlight](preview.png)

## What you see

- A dialog (`kind: "dialog"`, 920×640 px, Herdr's own frame), the window dimmed behind it. Nothing is added to the layout.
- **Search bar, 56px:** an 18px search glyph in `dim`, a borderless 16px field ("세션 제목, 대화 내용, 프로젝트로 검색…"), a 14px spinner while a search, the index or a resume is running, and an `esc` cap.
- **Filter chips, 40px:** five chips, each a 13px glyph, a 12px label and a chevron: 기간 (date), 프로젝트 (project or Space), 에이전트, 상태, 정렬. A chip whose filter is set is `accent` on an 10% accent tint. "필터 초기화" at the right when any is set. A chip opens a dropdown under it (a `Popup` anchored `top_left`): 30px rows, a check on the current value, project rows with their session count.
- A 1px `border` line, then the body, a 1px line and a 34px footer with key caps (`↑↓ 선택`, `↵ 이동|재개|열기`, `⇥ 필터`, `esc 닫기`) and, at the right, "N개 세션 · Nms", or an error in `blocked`, or a resume warning.
- **Body, left: the results**, 48% of the width (360–500px), a `v_virtual_list`:
  - With nothing typed and the recent sort: a "실행 중 N" section, then "최근 세션 N" (30px headers, 11px semibold `dim`).
  - Rows 58px (78px with a snippet), 6px in, 9px radius. Line 1: the agent's icon (20px: `icons/claude.svg`, `icons/codex.svg`, else a terminal glyph on `hover`), the title at 13.5px with matched words in `accent` semibold, and for a running session a pill: working = spinner + "작업 중" in `working`, blocked = "입력 대기" in `blocked`, else a dot + "실행 중". Archived Codex sessions say "보관됨". Line 2 (12px `dim`): `Space or project · agent · 오늘 14:32`. Line 3 only when the words matched the conversation and not all of them are in the title: "나" or "답" then a one-line snippet starting just before the first match, matches in `accent`.
  - Selected row on `selected`, hovered on `hover`.
- **Body, right: the preview** (hidden below 700px width): the icon (26px) and the title (15.5px semibold, two lines max), status pill and agent; a meta grid (프로젝트/Space, 디렉터리 in the terminal font, 브랜치, 시작, 마지막 활동 with a relative time, 메시지, 세션 ID); a 32px action bar on an accent tint saying exactly what Enter does ("↵ 실행 중인 터미널로 이동 · space › tab (t12)", "↵ 새 탭에서 재개 · claude --resume 1a2b3c4d…", or "재개할 수 없음 · why" in `blocked`); then "일치한 대화" / "최근 대화" with the message range, and the messages in a scroll area that opens on the matched one: the person's on `hover` headed "나", the agent's headed by its name in `accent`, the matched one outlined in `accent` with matching words on a 25% accent tint.
- Empty states are centered in `dim`: loading, first indexing, "“…”와 일치하는 세션이 없습니다", or no session for the filters, with a "필터 초기화" button when filters are on.

## How it behaves

- Opening shows the last list at once (kept in module scope), focuses the field, then in parallel: maps running terminals to sessions (`resolve`), updates the index incrementally (`index`), and searches. Typing searches 60 ms after the last key; only the newest answer is used. Running terminals are re-checked every 4 s while open.
- ↑/↓ and PageUp/PageDown move the selection (headers are skipped, the list scrolls only as far as needed). Click selects; clicking the selected row opens it. Tab / Shift+Tab walk the chip menus; in a menu ↑/↓ choose, Enter applies, ←/→ move to the next chip, Esc closes the menu. Esc closes the dialog.
- Typed operators narrow further and show in their chip: `project:` (substring of the project or Space name), `agent:claude|codex|other`, `after:` / `before:` (`YYYY-MM-DD`, `today`, `7d`, `2w`), `status:running|ended`, `sort:recent|created|relevance|oldest`. "사용자 지정…" in the date menu writes `after:<a week ago> before:<today>` into the field with the first date selected.
- **Enter on a running session:** `space.select`, `tab.select`, `pane.focus {terminal}` with its exact address; a sub-agent without a pane gets `agent.focus`, anything else `terminal.peek`. Nothing is started.
- **Enter on an ended session:** the engine checks the history file and folder still exist (else a warning in the footer, and the index is refreshed), then running terminals are mapped once more: if one runs the session now, it is focused instead. Otherwise the agent's launcher from `knownAgents()` (programs.json `run`) plus `--resume <id>` (Claude) or `resume <id> -C <folder>` (Codex) starts in a new tab named after the session, in the Space it was last seen in, else a Space on its folder, else a new Space on that folder. The same session can't be started twice within 15 s. A toast confirms.

## Built from

- **One mod**, `mods/session-spotlight/`: `main.js` (the View), `lib.js` (pure helpers, tested with node), `mod.json` (`place: "none"`, `overlay: {kind: "dialog", width: 920, height: 640}`), `icons/*.svg`, and `engine/` (Python 3.9+ standard library).
- **A `keys.json` snippet**: `"global": {"cmd-shift-k": "mod.open:session-spotlight"}`.
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
- Cmd+Shift+K opens the dialog with the field focused; Esc closes it.
- With nothing typed, running sessions come first, then sessions by last activity, each with project · agent · time.
- A word from a session's title lists it first; a word only said in a conversation lists it with a highlighted snippet, and the preview opens on that message.
- `agent:codex`, a date chip, the project chip and each sort change the list as named.
- Enter on a running session focuses its exact terminal, also when two Spaces share a name; the terminal count doesn't change.
- Enter on an ended Claude/Codex session starts `claude --resume <id>` / `codex resume <id> -C <folder>` in its folder; the new terminal maps back to the same session id.
- Enter on a session whose history file was deleted shows a warning and starts nothing.
