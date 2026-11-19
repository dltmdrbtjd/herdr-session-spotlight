# Changelog

## 0.1.0 — 2026-11-19

First local release (not published).

- Spotlight dialog (`Cmd+Shift+K`): search box, filter chips with dropdowns, virtualized result list, preview pane.
- Engine: Claude Code and Codex adapters, incremental SQLite FTS5 (trigram) index, query operators, relevance ranking, snippets, secret redaction.
- Live sessions: running terminals mapped to sessions by process (Claude pid files with start-time check, Codex open rollout, `--resume` argv).
- Open: exact-address focus for running sessions; resume in the session's folder for ended ones, with duplicate-start and missing-history checks.
- install / uninstall scripts that add or remove one `keys.json` binding with a backup.
