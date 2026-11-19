# Session Spotlight — 조사와 설계

[English](DESIGN.md) · **한국어**

## 1. 조사한 Herdr 환경 (herdr-app 0.1.16 / hc 0.1.21)

출처: `~/.config/herdr-app/AGENTS.md`, `herdr.d.ts`, `gpui-kit.d.ts`(앱이 시작할 때마다 다시 쓰는 정본), `herdr-app commands`, 실행 중인 앱에서의 프로브.

| 필요 | 사용한 공식 API | 확인 방법 |
|---|---|---|
| Space/Tab/Terminal/Agent 조회 | `spaces()`, `panes()`, `agents()`, `terminals()` | 임시 프로브 Mod로 실제 값 확인(`terminals()`에 `foreground.pid/argv`, `parent`, `labels`, `program` 포함) |
| 포커스 | `space.select {id}`, `tab.select {id}`, `pane.focus {terminal}`, `agent.focus {terminal}`, `terminal.peek` | `herdr-app commands` 인자 목록, 실제 앱 E2E |
| 새 탭/Space에서 실행 | `tab.new {space, folder, argv, name}`, `space.new {folder, argv, tab}` | 〃 |
| 모달 | `mod.json`의 `overlay: {kind: "dialog", width, height}` + `mod.open` (토글), `closeOverlay(props().overlay)` | shipped `picker`, `machine-add` |
| 드롭다운 | gpui-kit `Popup.new(id, trigger).anchor(...).content(...)` | dialog 안의 `absolute()` 패널은 그려지지 않아 교체 |
| 단축키 | `keys.json` `global` 섹션 `"cmd-k": "mod.open:session-spotlight"` | Herdr 키와 충돌 없음, `keys()`로 로드 확인. 처음 정한 `cmd-shift-k`는 Notion 데스크톱 앱의 macOS 전역 단축키에 먼저 잡혀(사용자 확인) 변경 |
| Tab 키 | `cx.bind_keys([{keystroke:"tab", action, context}])` + 루트 `key_context`/`on_action` | 앱이 Tab을 포커스 이동에 쓰기 때문 |
| 외부 프로세스 | `exec(cmd, args, {timeout})` (사용자 환경, 셸 없이 인자 배열) | 프로브로 PATH·python3 확인 |
| Mod 검증 | `herdr-app check <folder>`, `herdr-app status`(errors), `herdr-app shot` | 매 변경마다 실행 |
| 스크립트로 모달 조작 | `herdr-app do <mod>.<command>` → `nextCommand()` (열려 있는 copy에만, `:value` 불가) | E2E용 `scripts/drive.sh` |
| 언어 | 엔진이 설정의 `"language"`를 읽고(`auto`는 `defaults read -g AppleLocale`) 검색 응답마다 `"en"`/`"ko"`로 알려줌 | 설정 파일 출처를 하나로(리뷰 지적 반영) |

**Mod 런타임 제약**: DOM·Node API·`setTimeout` 없음, SQLite 없음, 파일 쓰기는 `~/.config/herdr-app` 아래만(`fs/promises`), `readTextFile`은 1 MiB까지. 그래서 SQLite FTS5 인덱스는 **Mod 폴더에 함께 들어 있는 최소 권한 로컬 인덱서 프로세스(Python 표준 라이브러리)** 로 분리했습니다. 네트워크·추가 패키지·데몬이 없고, Mod가 열릴 때 `exec`로 필요한 명령만 실행합니다.

## 2. 유사 오픈소스: herdr-omnisearch (MIT)

`dmnkf/herdr-omnisearch`(v0.17 계열)를 읽고 참고만 했습니다. 코드는 가져오지 않았습니다.

| 영역 | OmniSearch | Session Spotlight |
|---|---|---|
| 형태 | Herdr TUI 플러그인 + Herdr App용 팝업 Mod, `uv tool install`로 별도 CLI 설치 | Mod 하나(엔진 포함), 설치 스크립트로 복사만 |
| 범위 | 라이브 화면 텍스트 + 세션 아카이브(기본 꺼짐), TUI·원격 머신까지 | Claude/Codex 세션 기록 + Herdr 실행 중 터미널, 로컬만 |
| 인덱스 | live/app/archive 여러 SQLite, 주기적 watcher | 하나의 SQLite: 증분(바이트 오프셋) + FTS5 trigram |
| 실행 중 판정 | Claude pid 파일(부모 pid 포함), 명령줄 속 세션 id | Claude pid 파일 + **procStart 일치 검사**, Codex **열린 rollout 파일(lsof)**, argv 폴백 |
| UX | 92%×88% 팝업, Live/Sessions 모드 전환, 화면 미리보기 | 중앙 920×640 dialog, 단일 목록(열린 세션/최근 섹션), 필터 칩·연산자, 대화 미리보기 |

참고한 아이디어: 에이전트가 사용자 턴에 끼워 넣는 블록의 노이즈 목록, Claude `sessions/<pid>.json`으로 실행 중 세션 찾기, gpui 팝업 크기·zoom 처리와 Tab 바인딩 요령.
라이선스: MIT — 아이디어 참고는 제약이 없고, 코드를 복사하지 않았으므로 고지 의무도 없지만 README에 출처를 밝혔습니다.

## 3. 에이전트 기록 형식 (로컬에서 확인)

**Claude Code 2.1.283** — `~/.claude/projects/<cwd를 -로 바꾼 폴더>/<sessionId>.jsonl`
- `user`/`assistant` 레코드: `message.content`가 문자열 또는 `[{type: text|tool_use|tool_result|thinking|image}]`. `isMeta`, `isCompactSummary`, `isVisibleInTranscriptOnly`, `isSidechain` 플래그.
- 제목: `custom-title`(사용자 이름 변경) > `ai-title` > `summary` > `agent-name` > 첫 프롬프트.
- `cwd`는 세션 도중 셸의 `cd`를 따라 바뀜 → **첫 cwd**가 세션을 시작한(=재개해야 할) 폴더.
- `~/.claude/sessions/<pid>.json`: `{pid, sessionId, cwd, procStart: "Thu Nov 19 06:18:43 2026"(UTC, C locale), status, ...}` — 폴더 신뢰 전에는 생기지 않음.
- 하위 에이전트: `<sessionId>/subagents/agent-*.jsonl` (단독 재개 불가 → 기본 제외).
- 재개: `claude --resume <sessionId>` (해당 cwd에서).

**Codex CLI 0.169.1** — `~/.codex/sessions/YYYY/MM/DD/rollout-<시각>-<id>.jsonl`, `archived_sessions/*.jsonl(.zst)`
- `session_meta.payload`: `id, cwd, timestamp, source(cli|vscode|exec|{subagent}), cli_version, git`.
- `response_item` `type: message`, `role: developer|user|assistant`, `content[].type: input_text|output_text`. 사용자 턴에 `AGENTS.md` 지침·`<environment_context>`가 섞여 들어옴.
- 이름: `session_index.jsonl` `{id, thread_name}` (rollout 파일을 바꾸지 않음 → 매 인덱싱마다 반영).
- 실행 중인 codex는 자신의 rollout 파일을 열어 둠 → `lsof`로 정확히 식별.
- 재개: `codex resume <id> -C <dir>` (Herdr 런처 `codex --no-daemon` 앞에 붙음).

## 4. 아키텍처

```text
Session Spotlight
├── Spotlight UI .................. main.js (gpui-kit View, dialog overlay), i18n.js (en, ko)
├── Session Navigation ............ lib.js decideOpen / planFocus / resumeSpace / resumeArgv
├── Session Search Service ........ engine/search.py   (spotlight.py search|preview|check)
├── Session Adapters
│   ├── Herdr Live Sessions ....... lib.js liveTerminals + engine/live.py (spotlight.py resolve)
│   ├── Claude History ............ engine/adapters.py ClaudeAdapter
│   └── Codex History ............. engine/adapters.py CodexAdapter
└── Local Search Index ............ engine/store.py + indexer.py (spotlight.py index)
```

UI ↔ 엔진 경계는 JSON 한 객체입니다. 하이라이트는 `[text, matched]` 세그먼트로 넘겨 Python 코드포인트/JS UTF-16 오프셋 차이를 없앴습니다. 엔진이 사용자에게 보여줄 이유는 코드(`why_not_code`, `error`)와 함께 보내고, Mod가 그 코드를 현재 언어로 번역합니다.

### 데이터 모델

| 테이블 | 내용 |
|---|---|
| `sessions` | `id`(정수), `key`(=`머신|에이전트|세션ID`, unique), 제목·제목 출처, cwd·프로젝트·브랜치, 생성/마지막 활동, 메시지 수, 첫/마지막 프롬프트, 하위에이전트·보관 여부, 원본 경로 |
| `messages` | `id, sid, role, ts` — 일부러 좁게: FTS 결과 → 세션 매핑이 이 테이블 조회라 행이 작을수록 빠름(실측 2.3배) |
| `messages_fts` | FTS5 `trigram`, 텍스트 본문 (rowid = messages.id) |
| `sources` | 기록 파일별 `size, mtime_ns, offset, state(JSON)` — 증분 인덱싱 |
| `herdr_seen` | 세션이 마지막으로 실행되던 Herdr Space/탭/주소 — 프로젝트 필터와 재개 위치에 사용(로그로 복원할 수 없는 유일한 정보라 스키마 변경 시에도 유지) |
| `meta` | 스키마 버전, 설정 해시, 마지막 인덱싱 시각, 진행률 |

식별자: 세션 키는 머신·에이전트·세션ID로 충돌이 없고, 터미널은 herdr-core 주소(`t3n`, 원격은 `machine/t3`), Space·Tab은 Herdr id로만 다룹니다. **제목·프로젝트 이름으로 실행 중 터미널과 기록을 연결하지 않습니다.**

### 증분 인덱싱

`(size, mtime)` 동일 → 건너뜀 · **커졌고**, 같은 inode이며, 이미 읽은 부분의 앞 4KiB와 오프셋 직전 256바이트 해시가 그대로이고, 그 파일이 세션의 소유자일 때만 → 저장된 오프셋부터 파싱(미완성 마지막 줄은 다음 번으로) · 그 밖의 변경(같은 크기 재작성, 교체, 잘림, 세션 ID 변경) → 그 세션만 처음부터 다시 읽음 · 파일 삭제 → **그 파일이 소유한** 세션만 제거하고, 같은 세션의 다른 사본(예: `archived_sessions`)이 있으면 대신 읽음 · 제외 경로/옵션 변경 → 설정 해시가 달라져 전체 재구축 · 스키마 버전 변경 → 테이블 재생성. `flock`으로 인덱서는 하나만 실행되고, `reset`도 같은 잠금을 잡은 채 지웁니다.

### 검색과 점수

단어마다: 제목 10 · Space/프로젝트 6 · 첫 프롬프트 3 · 브랜치 3 · 폴더(홈 아래 경로) 2 · 에이전트 2 · 본문 `1.5×√min(일치 메시지 수, 25)`. 모든 단어가 어딘가에 있어야 하고(AND), 제목에 모든 단어가 있으면 +8, 제목과 완전히 같으면 +6, 최근성 `3·e^(−경과일/14)`, 실행 중 +1. 3글자 이상은 FTS trigram, 짧은 단어는 남은 후보 안에서 스캔.

## 5. 성능 (실측, 상세는 VERIFICATION.ko.md)

| 데이터 | 첫 인덱싱 | 변경 없음 | 검색(엔진) | 검색(Mod가 실행하는 프로세스 전체) |
|---|---|---|---|---|
| 실제 기록 212세션/7천 메시지 | 2.4–3.0s | 6ms | 1–26ms | 약 30–60ms |
| 합성 1,000세션/4만 메시지 | 2.1s | 10ms | 5–56ms | 중앙값 88–97ms |
| 합성 3,000세션/18만 메시지 | 10.3s | 27ms | 17–217ms | 중앙값 255ms |

합성 데이터는 20여 개 단어로만 만들어 거의 모든 단어가 모든 세션에 나오는 최악 조건입니다. 목표(100ms)는 1,000세션까지 충족, 3,000세션·18만 메시지의 다중 단어 검색은 초과합니다. 입력은 60ms 디바운스 + 최신 응답만 반영 + `exec` 비동기라 UI가 멈추지 않습니다.

## 6. 플랫폼 제약으로 구현하지 않은 것

- 과거 메시지 위치로 이동: Claude/Codex CLI에 해당 기능 없음 → 미리보기에서 일치 메시지로 스크롤.
- 원격 머신 기록 검색: 각 머신에 엔진 설치 + `exec({on})` + 명시적 허용 설정이 필요. 검증할 원격 머신이 없어 구현하지 않음.
- 종료된 Herdr 터미널(herdr-core finished 목록) 직접 검색: 정보가 제목·cwd뿐이고 Claude/Codex 기록이 더 정확해 사용하지 않음.
