# Verification (2026-11-19)

**English** · [한국어](VERIFICATION.ko.md)

Environment: macOS (Darwin 25.6, Apple Silicon), Herdr app 0.1.16 / herdr-core 0.1.21, Claude Code 2.1.283,
Codex CLI 0.169.1, Python 3.14.3 (and 3.9.6), SQLite 3.53.4 (and 3.51.0).
Real history: 175 Claude + 37 Codex sessions (212 sessions, 7,081 indexed messages; most of the ~1 GB of raw
JSONL is tool output, which is left out).

## Automated tests

| What | Run by | Result |
|---|---|---|
| Engine unit tests (`tests/engine`, 51): adapters, skipped noise, masking (parser state, before cutting), permissions, incremental indexing (append, equal-sized rewrite, replacement, delete, exclusion, schema change), archive moves, copies standing in, former owners, locks, reset race, search, operators, sorting, live mapping (procStart / startedAt, several Codex rollouts, argv suppression), preview, resume checks | lead + Herdr test-runner children | 51/51 on Python 3.14.3 and 3.9.6 |
| Mod logic (`tests/mod`, 23): dates, filter arguments, chips, live terminals, sub-agent placement, same-named Spaces, `decideOpen` refusals, resume target, launcher, status labels, English default and the Korean switch | lead + Herdr test-runner child | 23/23 |
| `herdr-app check mods/session-spotlight` | lead (every change) + test runner | passed |
| `spotlight.py doctor` | test runner | FTS5 trigram and zstd available, index `0600` |

## Scenarios in the real Herdr app

An open dialog was driven with `scripts/drive.sh` (`herdr-app do session-spotlight.<command>`), and the results were
read back with `herdr-app status`, `hc` and `herdr-app shot`. Test sessions were small `claude -p` (4) and
`codex exec` (1) runs with a unique token, made in a scratch folder and in this repository's folder; the test Spaces
and tabs were closed afterwards. These runs used the Korean UI that existed at the time; the English UI was then
checked with the same unit tests and `herdr-app check`.

| # | Scenario | Result | Evidence |
|---|---|---|---|
| 1 | Open and close | **partly** | `mod.open` opens it with the field focused, `closeOverlay` closes it. The user found `Cmd+Shift+K` taken by Notion → changed to `Cmd+K`, loaded per `keys()`. **Pressing `Cmd+K` / `Esc` by hand: not yet verified** |
| 2 | Recent list with nothing typed | passed | open sessions first, then recent ones by last activity, status pills |
| 3 | Claude title search | passed | "task tree" → the three title matches on top, highlighted |
| 4 | Codex search | passed | `agent:codex 리뷰`, the test token found the Codex session alone |
| 5 | Conversation search | passed | snippet starts just before the match; the preview scrolls to and highlights the matching message |
| 6 | Date and project filters | passed | Codex + last 30 days → 31; project `acme` (demo data) → 8; chips highlighted; dropdowns shown |
| 7 | Sorting | passed | oldest first puts Oct 22 on top; an archived Codex session says it can't be resumed |
| 8 | Same-named Spaces | passed | both test Spaces renamed `spotlight-same`; opening beta → alpha → beta focused the right Space id and pane id each time, terminal count 12 → 12 |
| 9 | Focusing an open session | passed | Enter from another Space → terminal count 11 → 11, focused pane = the session's pane |
| 10 | Resuming an ended session | **Claude passed / Codex partly** | Claude (trusted folder): a new tab in the existing Space, `claude --resume <id>`; the new process's `sessions/<pid>.json` has the original session id and the old conversation loaded. Claude (two new folders): `claude --resume <id>` in the right folder, stopped at Claude's own folder-trust screen (not answered), mapped to the same session through argv. Codex: `codex --no-daemon resume <id> -C <folder>` in a new Space, stopped at Codex's update notice (not touched) — **the Codex conversation loading itself wasn't seen** |
| 11 | A session whose history is gone | passed | file deleted while listed → Enter shows "history file was deleted", terminal count 14 → 14, and the index drops it |
| 12 | No results | passed | the "no sessions match" message and hint, empty preview |
| 13 | Large-index performance | measured | below |
| 14 | Index kept across a Herdr restart | **partly** | the index is a file outside the app (`~/.local/share/...`), kept across dozens of mod reloads and reopenings without a rebuild. **Herdr itself wasn't restarted, to avoid disturbing other running agents — not verified** |
| 15 | Existing mods and layouts | passed | `herdr-app status` errors `[]` throughout, no `*.error` files; `programs.json`, `lead-policy.md`, `reviewer.md`, `settings.json` untouched (modification times before the work started); `keys.json` got one line after a backup; no other mod changed |
| + | Sub-agent placement | passed | a child Claude started while another Space was focused showed up in its parent's place, with its session id; Enter used `agent.focus` (peek) |
| + | Status labels | passed | after a user report that idle agents looked "running": only working agents get the spinner, idle ones a gray Idle pill |

Not verified: the light theme on screen (only theme tokens are used; the user's theme wasn't switched), and windows
narrower than the 920 px dialog.

## Performance

The mod runs one process per search: `python3 -B -I -S spotlight.py search …` (about 30 ms to start).

**Real history (212 sessions, 7,081 messages)** — engine time / whole process (the timing method adds about 20 ms)

| Query | Engine | Process |
|---|---|---|
| (empty) | 1.5 ms | 49–54 ms |
| 프로필 | 5.4 ms | 53–57 ms |
| task tree | 14.2 ms | 62–69 ms |
| UI (two letters, scanned) | 25.6 ms | 74–82 ms |
| agent:codex 리뷰 | 1.7 ms | 49–51 ms |
| first index / nothing changed / a few appends | 2.4–3.0 s / 6 ms / 85 ms | |

**Synthetic data** (`scripts/bench.py`; about 20 words, so most words appear in nearly every session: a worst case)

| Size | Raw / index | First index | Nothing changed | 1% of files appended | Engine search medians | Process median |
|---|---|---|---|---|---|---|
| 1,000 sessions · 40k messages | 88 MB / 45 MB | 2.1 s | 10 ms | 12 ms | 5–56 ms | **88–97 ms** |
| 3,000 sessions · 180k messages | 396 MB / 186 MB | 10.3 s | 27 ms | 33 ms | 17–217 ms | **255 ms** |

- The 100 ms goal holds for the real history and for 1,000 synthetic sessions; multi-word and two-letter searches over
  3,000 sessions / 180k messages exceed it.
- Optimizations: FTS hits → sessions through a narrow table without text (38.8 → 16.9 ms per word); per-command
  imports and `-I -S` (start 50 → 30 ms).
- No UI freezes: search, indexing and previews all run through asynchronous `exec`; typing is debounced (60 ms), only
  the newest answer is used, and the result list is virtualized.

## Problems found and fixed during the work

| Problem | Found by | Fix |
|---|---|---|
| A title made from the first prompt stored a secret as is | engine test | titles and Codex thread names are masked too; the schema version forces a rebuild |
| Claude's `cwd` follows `cd` mid-session, so project and resume folder drifted | real history | the first `cwd` is the session's folder |
| `procStart` is UTC in the C locale, so a Korean-locale `ps` never matched | real pid files | `ps` runs with `TZ=UTC LC_ALL=C` |
| A path argument containing `claude-501` made a Codex terminal look like Claude | end-to-end run | the agent is decided by program name only (argv[0], or what a launcher shell runs) |
| A sub-agent's labels placed it in another Space | real app | placed by its parent terminal's pane |
| An index built by an older schema crashed search | upgrade | a read-only connection treats it as "not ready"; the next index run rebuilds |
| A query starting with `-` was read as an option | self-review | engine arguments are passed as `--name=value` |
| A failed preview stayed on "Loading" | self-review | error answers carry the session key, so the message shows |
| An `absolute()` dropdown inside the dialog never painted | real app | gpui-kit `Popup` |
| Idle agents showed a yellow "running" pill | user report | Herdr's agent status is shown as is |

## Independent review (Codex, Herdr's `reviewer` template, read-only) — two passes

The reviewer first stopped at Codex's folder-trust prompt; policy forbids the lead from answering it, so the user
approved it. The first reviewer terminal was closed by the lead's own mistake (it was attached to a test tab that the
lead closed) and was started again.

**Pass 1 (High 8 / Medium 3) — all confirmed and fixed**

| Finding | Fix |
|---|---|
| parser state (`sources.state`) kept unmasked prompts and titles, also for excluded files | state text masked; skipped and excluded files keep `{}` |
| `"password": "…"` (JSON keys) wasn't masked | quoted key / value patterns |
| a failed resolution or an unidentified Codex still led to a resume | Enter re-resolves; `decideOpen` refusal rules |
| focusing by a stale address (that terminal may run another session now) | go to the terminal that holds the session now |
| a Codex process with several rollouts open: the last one won | sub-agents set aside; several → unidentified |
| Claude pid files without `procStart` were trusted | only when `startedAt` is right after the process start |
| equal-sized rewrites / replacements treated as appends | only when grown, plus inode and prefix / pre-offset hashes |
| moving a rollout into the archive lost the session | only the owning file removes a session; a copy stands in |
| reset raced a running indexer | deletes under the same lock, keeps the lock file |
| keys.json: concurrent edits, symlinks, permissions | unique temp file, edits the target, keeps the mode, detects changes |
| uninstall removed bindings the user made | records and removes only what it added |

**Pass 2 (only the fixes; High 5 / Medium 5) — all confirmed and fixed**

| Finding | Fix |
|---|---|
| unmasked state stayed in existing indexes for unchanged files | schema 7 rebuilds |
| a 400-character preview cut before the closing quote defeated masking; values over 400 chars | mask before cutting; quoted values of any length, to the line end if unterminated |
| a former owner growing newer again: only its tail was read | append only by the current owner |
| a terminal that appeared during resolution wasn't covered | every terminal asked about must be in the answer, plus a terminal-set check right before launch |
| keys.json races between two installer runs | a lock, and the final change check after the temp file is ready |
| an owner truncated or turned into another session left no copy standing in | copies reconsidered whenever a session is given up |
| an ambiguous Codex pid could still get a session from argv | ambiguity blocks the argv fallback; a sub-agent rollout alone is unidentified |
| an unidentified open row could focus a pane where only the shell remained | only while an agent still runs there |
| an existing user binding got recorded as installed | not recorded when it already existed |
| one ownership record shared by every Herdr home | recorded per real keys.json path |

The policy allows two review/fix passes, so there was no third review; every fix got a regression test instead. The
tests were checked to catch the bugs: 12 fail against the pre-fix engine, and removing the ownership check alone fails
its test.

**Re-verified in the app after the fixes**

| Scenario | Result |
|---|---|
| resuming while an unidentified Claude terminal (a child on its trust screen) exists | refused, its address shown, no new terminal |
| resuming after that terminal is gone | `claude --resume` in a new tab; the new process's pid file has the original session id |
| Enter again on the resumed session | focused, nothing new started |
| a session whose folder is gone | "working folder is gone", no new terminal |
| scanning parser state after the real index was rebuilt | 0 secret-shaped values (5 of 220 sources are skipped / excluded and keep no state) |
