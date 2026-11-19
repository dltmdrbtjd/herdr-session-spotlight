// Session Spotlight: UI strings. English is the base; every key must exist in "en".
// A missing key in another language falls back to English. {name} is filled from params.
// Choose the language in ~/.config/herdr-session-spotlight/config.json: "language": "en" | "ko" | "auto".

export const STRINGS = {
  en: {
    placeholder: "Search sessions, conversations, projects…",
    engine_no_answer: "The search engine didn't answer",
    resolve_failed: "Couldn't check running sessions: {error}",
    index_failed: "Indexing failed: {error}",
    search_failed: "Search failed",
    moved_to_holder: "This session is open in {address}, so Spotlight went there.",
    just_resumed: "This session was resumed a moment ago. Try again shortly.",
    check_failed: "Couldn't check the session: {error}",
    terminals_changed: "Terminals changed while checking, so nothing was started. Press Enter again.",
    resumed_title: "Session resumed",
    archived: "Archived",
    snippet_you: "You",
    snippet_agent: "AI",
    clear_filters: "Clear filters",
    preview_empty: "Select a session to preview it",
    action_focus: "↵  Go to its open terminal · {where} ({address})",
    action_gone: "The terminal has closed",
    action_resume: "↵  Resume in a new tab · {command}",
    action_blocked: "Can't resume · {why}",
    action_preparing: "Preparing to resume…",
    ended: "Ended",
    meta_space: "Space",
    meta_project: "Project",
    meta_folder: "Folder",
    meta_branch: "Branch",
    meta_started: "Started",
    meta_last_active: "Last active",
    meta_messages: "Messages",
    meta_messages_count: "{n}",
    meta_session_id: "Session ID",
    live_unindexed: "This session's history isn't indexed yet. Open Spotlight again in a moment to see the conversation.",
    live_unknown: "This agent isn't Claude Code or Codex, or its session couldn't be identified. You can still go to its terminal.",
    conversation_matched: "Matching conversation",
    conversation_recent: "Recent conversation",
    loading: "Loading…",
    preview_failed: "Couldn't load the preview",
    no_messages: "No indexed conversation",
    loading_sessions: "Loading sessions…",
    first_index: "First run: indexing your session history…",
    no_match: "No sessions match “{query}”",
    no_match_hint: "Try other words or clear the filters",
    no_sessions: "No sessions match these filters",
    no_sessions_hint: "Try clearing the filters",
    count_sessions_one: "1 session",
    count_sessions: "{n} sessions",
    updating_index: "updating index",
    key_select: "Select",
    key_go: "Go to",
    key_resume: "Resume",
    key_open: "Open",
    key_filters: "Filters",
    key_close: "Close",
    section_open: "Open sessions",
    section_recent: "Recent sessions",
    status_working: "Working",
    status_blocked: "Needs input",
    status_done: "Done",
    status_idle: "Idle",
    date_all: "Any time",
    date_today: "Today",
    date_7d: "Last 7 days",
    date_30d: "Last 30 days",
    date_custom: "Custom range…",
    range_today: "today",
    agent_all: "All agents",
    agent_other: "Other",
    status_all: "Any status",
    status_open: "Open",
    status_ended: "Ended",
    sort_chip: "Sort",
    sort_auto: "Auto",
    sort_auto_hint: "Relevance while searching, otherwise last active",
    sort_recent: "Last active",
    sort_created: "Created",
    sort_relevance: "Relevance",
    sort_oldest: "Oldest",
    project_all: "All projects",
    when_today: "Today {time}",
    when_yesterday: "Yesterday {time}",
    when_this_year: "{month} {day}, {time}",
    when_other_year: "{month} {day}, {year}",
    when_full: "{month} {day}, {year} {time}",
    rel_now: "just now",
    rel_min: "{n} min ago",
    rel_hour: "{n} h ago",
    rel_day: "{n} d ago",
    open_no_selection: "No session selected",
    open_resolve_failed: "Couldn't check where sessions are running, so nothing was opened{reason}",
    open_missing: "Couldn't check terminal(s) {list}, so nothing was opened",
    open_agent_gone: "The agent in this terminal has exited",
    open_holder_unfocusable: "This session is open in {address}, but that terminal can't be focused",
    open_live_moved_on: "This terminal no longer runs this session",
    open_unknown_terminals: "A {agent} terminal couldn't be identified ({list}). To avoid starting a duplicate, nothing was resumed",
    open_cannot_resume: "This session can't be resumed",
    open_terminal_gone: "Terminal {address} is no longer running",
    // Codes the engine sends with `why_not` / `error`.
    why_unknown_agent: "No resume command is known for this agent",
    why_subagent: "A sub-agent transcript can't be resumed on its own",
    why_archived: "Archived in Codex. Unarchive it in Codex, then resume.",
    why_no_cwd: "No working folder is recorded, so it can't be resumed",
    why_missing_cwd: "The working folder is gone: {detail}",
    why_history_deleted: "The session's history file was deleted",
    err_not_found: "This session isn't in the index anymore. Its history may have been deleted.",
    err_no_index: "There is no index yet.",
  },
  ko: {
    placeholder: "세션 제목, 대화 내용, 프로젝트로 검색…",
    engine_no_answer: "검색 엔진이 응답하지 않았습니다",
    resolve_failed: "실행 중 세션 확인 실패: {error}",
    index_failed: "인덱싱 실패: {error}",
    search_failed: "검색 실패",
    moved_to_holder: "이 세션은 {address}에 열려 있어 그 터미널로 이동했습니다.",
    just_resumed: "방금 이 세션의 재개를 시작했습니다. 잠시 후 다시 시도하세요.",
    check_failed: "세션 확인 실패: {error}",
    terminals_changed: "확인하는 동안 실행 중인 터미널이 바뀌어 재개를 멈췄습니다. 다시 Enter를 누르세요.",
    resumed_title: "세션 재개",
    archived: "보관됨",
    snippet_you: "나",
    snippet_agent: "답",
    clear_filters: "필터 초기화",
    preview_empty: "세션을 선택하면 여기에 미리보기가 표시됩니다",
    action_focus: "↵  열려 있는 터미널로 이동 · {where} ({address})",
    action_gone: "터미널이 종료되었습니다",
    action_resume: "↵  새 탭에서 재개 · {command}",
    action_blocked: "재개할 수 없음 · {why}",
    action_preparing: "재개 준비 중…",
    ended: "종료됨",
    meta_space: "Space",
    meta_project: "프로젝트",
    meta_folder: "디렉터리",
    meta_branch: "브랜치",
    meta_started: "시작",
    meta_last_active: "마지막 활동",
    meta_messages: "메시지",
    meta_messages_count: "{n}개",
    meta_session_id: "세션 ID",
    live_unindexed: "이 세션의 기록이 아직 인덱스에 없습니다. 잠시 후 다시 열면 대화가 표시됩니다.",
    live_unknown: "Claude Code·Codex가 아닌 에이전트이거나 세션을 확인하지 못했습니다. 터미널로 이동만 할 수 있습니다.",
    conversation_matched: "일치한 대화",
    conversation_recent: "최근 대화",
    loading: "불러오는 중…",
    preview_failed: "미리보기를 불러오지 못했습니다",
    no_messages: "인덱싱된 대화가 없습니다",
    loading_sessions: "세션을 불러오는 중…",
    first_index: "처음 실행입니다. 세션 기록을 인덱싱하는 중…",
    no_match: "“{query}”와 일치하는 세션이 없습니다",
    no_match_hint: "다른 단어를 쓰거나 필터를 해제해 보세요",
    no_sessions: "조건에 맞는 세션이 없습니다",
    no_sessions_hint: "필터를 해제해 보세요",
    count_sessions_one: "1개 세션",
    count_sessions: "{n}개 세션",
    updating_index: "인덱스 갱신 중",
    key_select: "선택",
    key_go: "이동",
    key_resume: "재개",
    key_open: "열기",
    key_filters: "필터",
    key_close: "닫기",
    section_open: "열린 세션",
    section_recent: "최근 세션",
    status_working: "작업 중",
    status_blocked: "입력 대기",
    status_done: "완료",
    status_idle: "대기 중",
    date_all: "전체 기간",
    date_today: "오늘",
    date_7d: "최근 7일",
    date_30d: "최근 30일",
    date_custom: "사용자 지정…",
    range_today: "오늘",
    agent_all: "모든 에이전트",
    agent_other: "기타",
    status_all: "모든 상태",
    status_open: "열려 있음",
    status_ended: "종료됨",
    sort_chip: "정렬",
    sort_auto: "자동",
    sort_auto_hint: "검색어가 있으면 관련도, 없으면 최근 활동",
    sort_recent: "최근 활동순",
    sort_created: "생성일순",
    sort_relevance: "관련도순",
    sort_oldest: "오래된순",
    project_all: "모든 프로젝트",
    when_today: "오늘 {time}",
    when_yesterday: "어제 {time}",
    when_this_year: "{monthNum}월 {day}일 {time}",
    when_other_year: "{year}. {monthNum}. {day}.",
    when_full: "{year}. {monthNum}. {day}. {time}",
    rel_now: "방금",
    rel_min: "{n}분 전",
    rel_hour: "{n}시간 전",
    rel_day: "{n}일 전",
    open_no_selection: "선택된 세션이 없습니다",
    open_resolve_failed: "실행 중인 세션을 확인하지 못해 아무것도 열지 않았습니다{reason}",
    open_missing: "터미널({list})을 확인하지 못해 아무것도 열지 않았습니다",
    open_agent_gone: "이 터미널의 에이전트는 더 이상 실행 중이 아닙니다",
    open_holder_unfocusable: "이 세션은 {address}에서 실행 중이지만 그 터미널로 이동할 수 없습니다",
    open_live_moved_on: "이 터미널은 더 이상 이 세션을 실행하지 않습니다",
    open_unknown_terminals: "세션을 확인하지 못한 {agent} 터미널({list})이 있어, 중복 실행을 막으려고 재개하지 않았습니다",
    open_cannot_resume: "이 세션은 재개할 수 없습니다",
    open_terminal_gone: "터미널 {address}이(가) 더 이상 실행 중이 아닙니다",
    why_unknown_agent: "이 에이전트는 재개 명령을 알 수 없습니다",
    why_subagent: "하위 에이전트 기록은 단독으로 재개할 수 없습니다",
    why_archived: "Codex에서 보관(archive)된 세션입니다. Codex에서 보관을 해제한 뒤 재개하세요",
    why_no_cwd: "작업 디렉터리 정보가 없어 재개할 수 없습니다",
    why_missing_cwd: "작업 디렉터리가 없습니다: {detail}",
    why_history_deleted: "세션 기록 파일이 삭제되었습니다",
    err_not_found: "이 세션은 인덱스에 없습니다. 기록이 삭제되었을 수 있습니다.",
    err_no_index: "인덱스가 아직 없습니다.",
  },
};

export const LANGUAGES = Object.keys(STRINGS);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let current = "en";

/** "en", "ko"; anything else (or "auto" that found nothing) means English. */
export function setLanguage(lang) {
  current = STRINGS[lang] ? lang : "en";
  return current;
}

export function language() {
  return current;
}

/** Picks the language from a config value and, for "auto", the system locale (e.g. "ko_KR"). */
export function chooseLanguage(configured, systemLocale) {
  const want = String(configured || "en").toLowerCase();
  if (want !== "auto") return STRINGS[want] ? want : "en";
  const sys = String(systemLocale || "").toLowerCase().slice(0, 2);
  return STRINGS[sys] ? sys : "en";
}

export function t(key, params = {}) {
  const table = STRINGS[current] ?? STRINGS.en;
  let s = table[key] ?? STRINGS.en[key] ?? key;
  for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

/** Date pieces every language's patterns can use. */
export function dateParams(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return {
    year: d.getFullYear(),
    month: MONTHS[d.getMonth()],
    monthNum: d.getMonth() + 1,
    day: d.getDate(),
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

/** The engine's `why_not_code` / error code in the current language, or its own text. */
export function reason(code, detail, fallback) {
  const key = code ? (code.startsWith("why_") || code.startsWith("err_") ? code : `why_${code}`) : null;
  if (key && (STRINGS.en[key] || STRINGS.en[`err_${code}`])) {
    return t(STRINGS.en[key] ? key : `err_${code}`, { detail: detail ?? "" });
  }
  return fallback || "";
}
