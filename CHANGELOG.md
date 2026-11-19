# Changelog

## 0.1.0 — 2026-11-19

First local release (not published).

- Spotlight dialog (`Cmd+K`; Cmd+Shift+K was taken system-wide by the Notion app): search box, filter chips with dropdowns, virtualized result list, preview pane.
- Engine: Claude Code and Codex adapters, incremental SQLite FTS5 (trigram) index, query operators, relevance ranking, snippets, secret redaction.
- Live sessions: running terminals mapped to sessions by process (Claude pid files with start-time check, Codex open rollout, `--resume` argv).
- Open: exact-address focus for running sessions; resume in the session's folder for ended ones, with duplicate-start and missing-history checks.
- install / uninstall scripts that add or remove one `keys.json` binding with a backup.
- Two independent Codex review passes, all findings fixed with regression tests: masked parser state and prompts cut after masking, JSON-key secrets, append only after an inode/prefix fingerprint check and only by the owning file, archived copies standing in for a session, reset under the indexer lock, stricter Claude pid-file and Codex rollout identification, Enter re-resolving and refusing on any uncertainty, keys.json edits that are locked, symlink-safe and only undo what they added.
- Open sessions show Herdr's agent status (작업 중 / 입력 대기 / 완료 / 대기 중) instead of "실행 중" for every agent alive in a terminal; the section reads "열린 세션" and the status filter "열려 있음".
- English is now the base language of the UI and the docs; Korean is a setting away (`"language": "ko"` or `"auto"` in the config) and the docs have Korean versions (`*.ko.md`). The engine sends English messages with codes the mod translates.
