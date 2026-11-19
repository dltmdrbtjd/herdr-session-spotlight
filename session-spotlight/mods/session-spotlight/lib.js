// Session Spotlight: pure helpers. Nothing here touches Herdr or gpui-kit, so the
// node tests in tests/mod exercise exactly what the mod runs.

export const AGENT_LABEL = { claude: "Claude Code", codex: "Codex" };

export const DATE_OPTIONS = [
  { value: "all", label: "전체 기간" },
  { value: "today", label: "오늘" },
  { value: "7d", label: "최근 7일" },
  { value: "30d", label: "최근 30일" },
  { value: "custom", label: "사용자 지정…" },
];
export const AGENT_OPTIONS = [
  { value: "all", label: "모든 에이전트" },
  { value: "claude", label: "Claude" },
  { value: "codex", label: "Codex" },
  { value: "other", label: "기타" },
];
export const STATUS_OPTIONS = [
  { value: "all", label: "모든 상태" },
  { value: "running", label: "열려 있음" },
  { value: "ended", label: "종료됨" },
];
export const SORT_OPTIONS = [
  { value: "auto", label: "자동", hint: "검색어가 있으면 관련도, 없으면 최근 활동" },
  { value: "recent", label: "최근 활동순" },
  { value: "created", label: "생성일순" },
  { value: "relevance", label: "관련도순" },
  { value: "oldest", label: "오래된순" },
];
export const FILTER_KINDS = ["date", "project", "agent", "status", "sort"];

export const DEFAULT_FILTERS = Object.freeze({ date: "all", project: null, agent: "all", status: "all", sort: "auto" });

const pad = (n) => String(n).padStart(2, "0");
const DAY = 86400000;

function startOfDay(ms) {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** "오늘 14:32", "어제 09:10", "11월 3일 14:32", "2025. 9. 17." */
export function formatWhen(sec, nowMs = Date.now()) {
  if (!sec) return "";
  const ms = sec * 1000;
  const d = new Date(ms);
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const today = startOfDay(nowMs);
  if (ms >= today) return `오늘 ${hm}`;
  if (ms >= today - DAY) return `어제 ${hm}`;
  if (d.getFullYear() === new Date(nowMs).getFullYear()) return `${d.getMonth() + 1}월 ${d.getDate()}일 ${hm}`;
  return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}.`;
}

/** Full date for the preview: "2026. 11. 19. 14:32" */
export function formatFull(sec) {
  if (!sec) return "—";
  const d = new Date(sec * 1000);
  return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}. ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatRelative(sec, nowMs = Date.now()) {
  if (!sec) return "";
  const diff = Math.max(0, nowMs - sec * 1000);
  if (diff < 60000) return "방금";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}분 전`;
  if (diff < DAY) return `${Math.floor(diff / 3600000)}시간 전`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}일 전`;
  return formatWhen(sec, nowMs);
}

export function dateFromSec(sec) {
  const d = new Date(sec * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Arguments for `spotlight.py search`. */
export function searchArgs(query, filters, liveJson, limit = 80) {
  const f = { ...DEFAULT_FILTERS, ...(filters || {}) };
  // `--name=value`: a value starting with "-" ("-foo", "--resume") must not read as an option.
  const args = ["search", `--query=${query || ""}`, "--limit", String(limit)];
  if (f.agent && f.agent !== "all") args.push("--agent", f.agent);
  if (f.project) args.push(`--project=${f.project}`);
  if (f.date && f.date !== "all" && f.date !== "custom") args.push("--since", f.date);
  if (f.status && f.status !== "all") args.push("--status", f.status);
  if (f.sort && f.sort !== "auto") args.push("--sort", f.sort);
  if (liveJson) args.push(`--live=${liveJson}`);
  return args;
}

/** What a chip says. Operators typed in the field show in the chip they narrow. */
export function chipLabel(kind, filters, parsed) {
  const f = { ...DEFAULT_FILTERS, ...(filters || {}) };
  const find = (opts, v) => opts.find((o) => o.value === v)?.label ?? v;
  if (kind === "date") {
    if (parsed?.after || parsed?.before) {
      const a = parsed.after ? dateFromSec(parsed.after).slice(5).replace("-", "/") : "";
      const b = parsed.before ? dateFromSec(parsed.before - 1).slice(5).replace("-", "/") : "";
      return `${a || "…"} – ${b || "오늘"}`;
    }
    return find(DATE_OPTIONS, f.date);
  }
  if (kind === "project") return parsed?.project || f.project || "모든 프로젝트";
  if (kind === "agent") return parsed?.agent ? find(AGENT_OPTIONS, parsed.agent) : find(AGENT_OPTIONS, f.agent);
  if (kind === "status") return parsed?.status ? find(STATUS_OPTIONS, parsed.status) : find(STATUS_OPTIONS, f.status);
  if (kind === "sort") return parsed?.sort ? find(SORT_OPTIONS, parsed.sort) : f.sort === "auto" ? "정렬" : find(SORT_OPTIONS, f.sort);
  return "";
}

export function chipActive(kind, filters, parsed) {
  const f = { ...DEFAULT_FILTERS, ...(filters || {}) };
  if (kind === "date") return f.date !== "all" || Boolean(parsed?.after || parsed?.before);
  if (kind === "project") return Boolean(f.project || parsed?.project);
  if (kind === "agent") return f.agent !== "all" || Boolean(parsed?.agent);
  if (kind === "status") return f.status !== "all" || Boolean(parsed?.status);
  if (kind === "sort") return f.sort !== "auto" || Boolean(parsed?.sort);
  return false;
}

/** Menu options for a chip. Project options come from the engine's facets. */
export function menuOptions(kind, facets) {
  if (kind === "date") return DATE_OPTIONS;
  if (kind === "agent") return AGENT_OPTIONS;
  if (kind === "status") return STATUS_OPTIONS;
  if (kind === "sort") return SORT_OPTIONS;
  if (kind === "project") {
    const list = (facets?.projects ?? []).map(([name, count]) => ({ value: name, label: name, count }));
    return [{ value: null, label: "모든 프로젝트" }, ...list];
  }
  return [];
}

/** ` after:YYYY-MM-DD before:YYYY-MM-DD` appended to the query for a custom range. */
export function customRangeQuery(query, nowMs = Date.now()) {
  const stripped = (query || "").replace(/\s*\b(after|before|since|until):\S+/g, "").trim();
  const from = dateFromSec((nowMs - 7 * DAY) / 1000);
  const to = dateFromSec(nowMs / 1000);
  const range = `after:${from} before:${to}`;
  return { text: stripped ? `${stripped} ${range}` : range, select: [stripped ? stripped.length + 7 : 6, (stripped ? stripped.length + 7 : 6) + 10] };
}

// ---------------------------------------------------------------------------
// Live terminals

const AGENT_KEYS = new Set(["claude", "codex"]);

export function machineOf(address) {
  const i = (address || "").indexOf("/");
  return i > 0 ? address.slice(0, i) : null;
}

/**
 * The terminals worth listing as sessions: agents (they report a status), and
 * Claude/Codex terminals that haven't reported yet. Plain shells stay out.
 * `world` = { terminals, agents, panes, spaces } as Herdr gives them.
 */
export function liveTerminals(world) {
  const agentsBy = new Map((world.agents ?? []).map((a) => [a.address, a]));
  const paneBy = new Map((world.panes ?? []).filter((p) => p.terminal).map((p) => [p.terminal, p]));
  const tabInfo = new Map();
  for (const s of world.spaces ?? []) for (const t of s.tabs ?? []) tabInfo.set(t.id, { tab: t, space: s });
  const termBy = new Map((world.terminals ?? []).map((t) => [t.address, t]));
  // Where a terminal lives, as Herdr shows it: its own pane's tab; a sub-agent (no pane)
  // belongs to its parent's tab. Labels come last: a sub-agent's can name whatever space
  // was focused when it was started.
  const tabOf = (address, depth = 0) => {
    const pane = paneBy.get(address);
    if (pane) return pane.tab;
    const t = termBy.get(address);
    if (t?.parent && depth < 8) {
      const up = tabOf(t.parent, depth + 1);
      if (up) return up;
    }
    return agentsBy.get(address)?.tab ?? t?.labels?.["herdr.tab"] ?? "";
  };
  const out = [];
  for (const t of world.terminals ?? []) {
    if (t.state !== "live") continue;
    const a = agentsBy.get(t.address);
    const key = t.program?.key ?? "";
    const isAgent = Boolean(a || t.report || AGENT_KEYS.has(key) || t.program?.agent);
    if (!isAgent) continue;
    const pane = paneBy.get(t.address);
    const tabId = tabOf(t.address);
    const info = tabInfo.get(tabId);
    if (!info && !a) continue; // not shown anywhere in Herdr (another app's terminal)
    const remote = Boolean(machineOf(t.address));
    out.push({
      address: t.address,
      pid: remote ? null : t.pid ?? null,
      fg_pid: remote ? null : t.foreground?.pid ?? null,
      fg_argv: t.foreground?.argv ?? t.argv ?? [],
      app: t.report?.app ?? a?.app ?? null,
      program: key,
      program_name: t.program?.name ?? key,
      title: a?.title || t.title || pane?.title || "",
      cwd: pane?.cwd ?? t.foreground?.cwd ?? t.cwd ?? "",
      branch: pane?.branch ?? "",
      pane: pane?.pane ?? "",
      space_id: info?.space.id ?? "",
      space_name: info?.space.name ?? "",
      tab_id: tabId,
      tab_name: info?.tab.name ?? "",
      parent: t.parent ?? null,
      status: a?.status ?? (typeof t.status === "string" ? t.status : "") ?? "",
      created_ms: t.created_ms ?? 0,
      changed_ms: info?.tab.changed_at ?? t.status_ms ?? 0,
      remote,
    });
  }
  return out;
}

/** The engine's `resolve` input: only what it needs to look at processes. */
export function resolveInput(live) {
  return live.filter((t) => !t.remote).map((t) => ({ address: t.address, pid: t.pid, fg_pid: t.fg_pid, fg_argv: t.fg_argv, app: t.app, program: t.program, space_id: t.space_id, space_name: t.space_name, tab_id: t.tab_id, tab_name: t.tab_name }));
}

/** Fingerprint of which processes run where; resolve again when it changes. */
export function liveFingerprint(live) {
  return live.map((t) => `${t.address}:${t.fg_pid ?? ""}`).sort().join(",");
}

/** The engine's `search --live` input: live terminals with the session each one holds. */
export function liveForSearch(live, resolved) {
  return {
    terminals: live.map((t) => {
      const r = resolved?.[t.address];
      const agent = r?.agent ?? (AGENT_KEYS.has(t.program) ? t.program : t.program || "other");
      return {
        address: t.address, agent, session_id: r?.session_id ?? null, title: t.title, cwd: t.cwd, branch: t.branch,
        pane: t.pane, space_id: t.space_id, space_name: t.space_name, tab_id: t.tab_id, tab_name: t.tab_name,
        status: t.status, program: t.program_name, created_ms: t.created_ms, changed_ms: t.changed_ms,
      };
    }),
  };
}

// ---------------------------------------------------------------------------
// The list

/**
 * How an open session's agent status reads, as Herdr reports it (OSC 7501). An agent waiting
 * for input is open but not running anything: it must not look like it's working.
 *   tone: the theme color name (working, blocked, done, idle)
 */
export function statusLabel(status) {
  if (status === "working") return { label: "작업 중", tone: "working", spin: true };
  if (status === "blocked") return { label: "입력 대기", tone: "blocked" };
  if (status === "done") return { label: "완료", tone: "done" };
  return { label: "대기 중", tone: "idle" };
}

export const ROW_H = 58;
export const ROW_SNIPPET_H = 78;
export const HEAD_H = 30;

export function showsSnippet(r) {
  return Boolean(r?.snippet?.segments?.length) && !r.title_has_all;
}

/** Rows for the virtual list: section headers when nothing is typed, then results. */
export function listItems(results, { query, sort }) {
  const items = [];
  const typed = Boolean((query || "").trim());
  if (!typed && (sort === "auto" || sort === "recent")) {
    const running = results.filter((r) => r.running);
    const rest = results.filter((r) => !r.running);
    if (running.length) {
      items.push({ kind: "head", key: "h-running", label: "열린 세션", count: running.length });
      running.forEach((r) => items.push({ kind: "row", key: r.key, r }));
    }
    if (rest.length) {
      items.push({ kind: "head", key: "h-recent", label: "최근 세션", count: rest.length });
      rest.forEach((r) => items.push({ kind: "row", key: r.key, r }));
    }
    return items;
  }
  results.forEach((r) => items.push({ kind: "row", key: r.key, r }));
  return items;
}

export function itemHeight(item) {
  if (item.kind === "head") return HEAD_H;
  return showsSnippet(item.r) ? ROW_SNIPPET_H : ROW_H;
}

/** Next selectable index from `at` moving by `step`, skipping headers, clamped. */
export function moveSelection(items, at, step) {
  const rows = items.map((it, i) => (it.kind === "row" ? i : -1)).filter((i) => i >= 0);
  if (!rows.length) return -1;
  const pos = rows.indexOf(at);
  if (pos < 0) return step >= 0 ? rows[0] : rows[rows.length - 1];
  return rows[Math.max(0, Math.min(rows.length - 1, pos + step))];
}

export function firstRow(items) {
  return items.findIndex((it) => it.kind === "row");
}

/** Splits highlighted segments into words for a wrapping layout. */
export function wrapWords(segments, limit = 400) {
  const out = [];
  for (const [text, hit] of segments ?? []) {
    const parts = String(text).replace(/\s+/g, " ").split(" ");
    for (const w of parts) if (w) out.push([w, hit]);
    if (out.length > limit) break;
  }
  return out.slice(0, limit);
}

// ---------------------------------------------------------------------------
// Navigation

/**
 * What Enter does, decided on a fresh `resolve` answer (never on the list's cached one):
 *   { kind: "focus", address, steps } | { kind: "resume" } | { kind: "blocked", message }
 * A session is focused where a terminal holds it now, by that terminal's exact address.
 * Nothing is started while any terminal of the same agent couldn't be identified, or when
 * the holder can't be focused: a duplicate of a running session is worse than a refusal.
 */
export function decideOpen(r, resolved, world, asked = null) {
  if (!r) return { kind: "blocked", message: "선택된 세션이 없습니다" };
  if (!resolved || resolved.ok === false || !Array.isArray(resolved.terminals)) {
    return { kind: "blocked", message: `실행 중인 세션을 확인하지 못해 아무것도 열지 않았습니다${resolved?.message ? `: ${resolved.message}` : ""}` };
  }
  const list = resolved.terminals;
  // Every terminal that was asked about must be in the answer; a gap is an unknown.
  const missing = (asked ?? []).filter((a) => !list.some((t) => t.address === a));
  if (missing.length) {
    return { kind: "blocked", message: `터미널(${missing.join(", ")})을 확인하지 못해 아무것도 열지 않았습니다` };
  }
  if (r.kind === "live" && !r.session_id) {
    // An agent Spotlight can't identify (not Claude/Codex): its terminal, if an agent still runs there.
    const address = r.running?.address;
    const still = address && liveTerminals(world).some((t) => t.address === address);
    return still ? planFocus(address, world) : { kind: "blocked", message: "이 터미널의 에이전트는 더 이상 실행 중이 아닙니다" };
  }
  const holder = list.find((t) => t.agent === r.agent && t.session_id && t.session_id === r.session_id);
  if (holder) {
    const plan = planFocus(holder.address, world);
    if (plan.kind === "focus") return plan;
    return { kind: "blocked", message: `이 세션은 ${holder.address}에서 실행 중이지만 그 터미널로 이동할 수 없습니다` };
  }
  if (r.kind === "live") return { kind: "blocked", message: "이 터미널은 더 이상 이 세션을 실행하지 않습니다" };
  const unknown = list.filter((t) => t.agent === r.agent && !t.session_id).map((t) => t.address);
  if (unknown.length) {
    const who = AGENT_LABEL[r.agent] ?? r.agent;
    return { kind: "blocked", message: `세션을 확인하지 못한 ${who} 터미널(${unknown.join(", ")})이 있어, 중복 실행을 막으려고 재개하지 않았습니다` };
  }
  if (!r.resumable) return { kind: "blocked", message: r.why_not || "이 세션은 재개할 수 없습니다" };
  return { kind: "resume" };
}

export function planFocus(address, world) {
  const pane = (world.panes ?? []).find((p) => p.terminal === address);
  if (pane) {
    const space = (world.spaces ?? []).find((s) => (s.tabs ?? []).some((t) => t.id === pane.tab));
    const steps = [];
    if (space) steps.push(["space.select", { id: space.id }]);
    steps.push(["tab.select", { id: pane.tab }]);
    steps.push(["pane.focus", { terminal: address }]);
    return { kind: "focus", address, space: space?.id ?? null, tab: pane.tab, steps };
  }
  if ((world.agents ?? []).some((a) => a.address === address)) {
    return { kind: "focus", address, steps: [["agent.focus", { terminal: address }]] };
  }
  if ((world.terminals ?? []).some((t) => t.address === address && t.state === "live")) {
    return { kind: "focus", address, steps: [["terminal.peek", { terminal: address }]] };
  }
  return { kind: "blocked", message: `터미널 ${address}이(가) 더 이상 실행 중이 아닙니다` };
}

/** The space a resumed session opens in: where it last ran, else one on its folder. */
export function resumeSpace(r, world) {
  const local = (world.spaces ?? []).filter((s) => !s.machine);
  if (r.last_space_id) {
    const seen = local.find((s) => s.id === r.last_space_id);
    if (seen) return seen.id;
  }
  const cwd = (r.cwd || "").replace(/\/+$/, "");
  if (!cwd) return null;
  const byFolder = local.find((s) => (s.folder || "").replace(/\/+$/, "") === cwd);
  if (byFolder) return byFolder.id;
  const tabs = new Map();
  for (const s of local) for (const t of s.tabs ?? []) tabs.set(t.id, s.id);
  const pane = (world.panes ?? []).find((p) => p.cwd && p.cwd.replace(/\/+$/, "") === cwd && tabs.has(p.tab));
  return pane ? tabs.get(pane.tab) : null;
}

/** The person's own launcher for the agent (programs.json `run`), then the resume arguments. */
export function resumeArgv(r, known) {
  const entry = (known ?? []).find((k) => k.key === r.agent && k.installed !== false && Array.isArray(k.run) && k.run.length);
  const base = entry ? [...entry.run] : [r.agent];
  return [...base, ...(r.resume_args ?? [])];
}

export function tabName(r) {
  const title = (r.title || "").trim();
  if (!title) return undefined;
  return title.length > 36 ? `${title.slice(0, 35)}…` : title;
}

/** UTF-8 hex (used by scripted checks, where command names can't carry other characters). */
export function fromHex(hex) {
  const bytes = [];
  for (let i = 0; i + 1 < (hex || "").length; i += 2) bytes.push(parseInt(hex.slice(i, i + 2), 16));
  let out = "";
  for (let i = 0; i < bytes.length; ) {
    const b = bytes[i];
    const n = b >= 0xf0 ? 4 : b >= 0xe0 ? 3 : b >= 0xc0 ? 2 : 1;
    let cp = n === 1 ? b : b & (0xff >> (n + 1));
    for (let j = 1; j < n; j++) cp = (cp << 6) | (bytes[i + j] & 0x3f);
    out += String.fromCodePoint(cp);
    i += n;
  }
  return out;
}
