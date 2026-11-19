// Tests for the mod's pure logic. Run: node --test tests/mod
import test from "node:test";
import assert from "node:assert/strict";
import * as L from "../../session-spotlight/mods/session-spotlight/lib.js";

const at = (y, m, d, h = 0, min = 0) => new Date(y, m - 1, d, h, min).getTime() / 1000;
const NOW = new Date(2026, 10, 19, 15, 0).getTime();

test("formatWhen: today, yesterday, this year, older", () => {
  assert.equal(L.formatWhen(at(2026, 11, 19, 14, 32), NOW), "오늘 14:32");
  assert.equal(L.formatWhen(at(2026, 11, 18, 9, 5), NOW), "어제 09:05");
  assert.equal(L.formatWhen(at(2026, 11, 3, 8, 0), NOW), "11월 3일 08:00");
  assert.equal(L.formatWhen(at(2025, 9, 17), NOW), "2025. 9. 17.");
  assert.equal(L.formatWhen(0, NOW), "");
});

test("formatRelative", () => {
  assert.equal(L.formatRelative(NOW / 1000 - 20, NOW), "방금");
  assert.equal(L.formatRelative(NOW / 1000 - 600, NOW), "10분 전");
  assert.equal(L.formatRelative(NOW / 1000 - 7200, NOW), "2시간 전");
  assert.equal(L.formatRelative(NOW / 1000 - 3 * 86400, NOW), "3일 전");
});

test("searchArgs carries only non-default filters", () => {
  assert.deepEqual(L.searchArgs("프로필", L.DEFAULT_FILTERS, null, 50), ["search", "--query=프로필", "--limit", "50"]);
  const args = L.searchArgs("x", { date: "7d", project: "acme-web", agent: "codex", status: "running", sort: "oldest" }, '{"terminals":[]}', 10);
  assert.deepEqual(args, ["search", "--query=x", "--limit", "10", "--agent", "codex", "--project=acme-web", "--since", "7d", "--status", "running", "--sort", "oldest", '--live={"terminals":[]}']);
  assert.deepEqual(L.searchArgs("-foo --resume", L.DEFAULT_FILTERS).slice(0, 2), ["search", "--query=-foo --resume"]);
  assert.ok(!L.searchArgs("", { ...L.DEFAULT_FILTERS, date: "custom" }).includes("--since"));
});

test("chip labels follow filters and typed operators", () => {
  assert.equal(L.chipLabel("date", L.DEFAULT_FILTERS, {}), "전체 기간");
  assert.equal(L.chipLabel("agent", { agent: "codex" }, {}), "Codex");
  assert.equal(L.chipLabel("agent", L.DEFAULT_FILTERS, { agent: "claude" }), "Claude");
  assert.equal(L.chipLabel("project", L.DEFAULT_FILTERS, { project: "acme-web" }), "acme-web");
  assert.equal(L.chipLabel("date", L.DEFAULT_FILTERS, { after: at(2026, 11, 1), before: at(2026, 11, 11) }), "11/01 – 11/10");
  assert.ok(L.chipActive("status", { status: "ended" }, {}));
  assert.ok(!L.chipActive("sort", L.DEFAULT_FILTERS, {}));
});

test("customRangeQuery appends a week and selects the start date", () => {
  const { text, select } = L.customRangeQuery("버그 after:2020-01-01", NOW);
  assert.equal(text, "버그 after:2026-11-12 before:2026-11-19");
  assert.equal(text.slice(select[0], select[1]), "2026-11-12");
});

const world = {
  spaces: [
    { id: "spA", name: "same", machine: null, folder: "/w/a", tabs: [{ id: "tbA", name: "Claude Lead", changed_at: 5 }] },
    { id: "spB", name: "same", machine: null, folder: "/w/b", tabs: [{ id: "tbB", name: "Claude Lead", changed_at: 6 }] },
    { id: "vps/spC", name: "remote", machine: "vps", folder: "/srv", tabs: [{ id: "vps/tbC", name: "1" }] },
  ],
  panes: [
    { pane: "pA", terminal: "t1", tab: "tbA", cwd: "/w/a" },
    { pane: "pB", terminal: "t2", tab: "tbB", cwd: "/w/b" },
    { pane: "pS", terminal: "t5", tab: "tbB", cwd: "/w/b" },
    { pane: "pC", terminal: "vps/t3", tab: "vps/tbC", cwd: "/srv" },
  ],
  agents: [
    { address: "t1", tab: "tbA", space: "spA", space_name: "same", tab_name: "Claude Lead", status: "idle", app: "claude-code", title: "A" },
    { address: "t2", tab: "tbB", space: "spB", space_name: "same", tab_name: "Claude Lead", status: "working", app: "claude-code", title: "B" },
    { address: "t9", tab: "tbB", space: "spB", space_name: "same", tab_name: "Claude Lead", status: "idle", app: "codex", title: "sub-agent" },
  ],
  terminals: [
    { address: "t1", state: "live", pid: 10, foreground: { pid: 11, argv: ["claude"] }, program: { key: "claude", name: "Claude Code", agent: true }, report: { app: "claude-code" }, labels: {} },
    { address: "t2", state: "live", pid: 20, foreground: { pid: 21, argv: ["claude"] }, program: { key: "claude", name: "Claude Code", agent: true }, report: { app: "claude-code" }, labels: {} },
    { address: "t5", state: "live", pid: 50, foreground: { pid: 50, argv: ["zsh"] }, program: { key: "shell", name: "zsh", shell: true }, labels: {} },
    { address: "vps/t3", state: "live", pid: 30, foreground: { pid: 31, argv: ["codex"] }, program: { key: "codex", name: "Codex", agent: true }, labels: {} },
    { address: "t9", state: "live", pid: 90, foreground: { pid: 91, argv: ["codex"] }, program: { key: "codex", name: "Codex", agent: true }, report: { app: "codex" }, labels: {} },
    { address: "t7", state: "finished", pid: 70, program: { key: "claude" }, labels: {} },
    { address: "t8", state: "live", pid: 80, program: { key: "claude" }, labels: {} },
  ],
};

test("liveTerminals: agents only, shells and other apps' terminals out, remote has no pids", () => {
  const live = L.liveTerminals(world);
  assert.deepEqual(live.map((t) => t.address), ["t1", "t2", "vps/t3", "t9"]);
  const remote = live.find((t) => t.address === "vps/t3");
  assert.equal(remote.remote, true);
  assert.equal(remote.pid, null);
  assert.equal(live[0].space_id, "spA");
  assert.equal(live[1].space_id, "spB");
  assert.deepEqual(L.resolveInput(live).map((t) => t.address), ["t1", "t2", "t9"]);
});

test("liveForSearch attaches resolved session ids by address", () => {
  const live = L.liveTerminals(world);
  const out = L.liveForSearch(live, { t1: { agent: "claude", session_id: "S1" } });
  assert.equal(out.terminals[0].session_id, "S1");
  assert.equal(out.terminals[1].session_id, null);
  assert.equal(out.terminals[1].agent, "claude");
});

const ok = (terminals) => ({ ok: true, terminals });

test("decideOpen focuses the exact terminal that holds the session, even when spaces share a name", () => {
  const r = { key: "k", agent: "claude", session_id: "S2", running: { address: "t1" } }; // list says t1: stale
  const plan = L.decideOpen(r, ok([{ address: "t1", agent: "claude", session_id: "S1" }, { address: "t2", agent: "claude", session_id: "S2" }]), world);
  assert.equal(plan.kind, "focus");
  assert.deepEqual(plan.steps, [["space.select", { id: "spB" }], ["tab.select", { id: "tbB" }], ["pane.focus", { terminal: "t2" }]]);
  const other = L.decideOpen({ ...r, session_id: "S1" }, ok([{ address: "t1", agent: "claude", session_id: "S1" }]), world);
  assert.deepEqual(other.steps[0], ["space.select", { id: "spA" }]);
});

test("decideOpen: a session whose terminal now runs another one is not focused there", () => {
  const r = { key: "k", kind: "session", agent: "claude", session_id: "A", running: { address: "t1" }, resumable: true };
  assert.equal(L.decideOpen(r, ok([{ address: "t1", agent: "claude", session_id: "B" }]), world).kind, "resume");
});

test("decideOpen never starts anything on an incomplete or failed answer", () => {
  const r = { key: "k", kind: "session", agent: "codex", session_id: "X", resumable: true };
  assert.equal(L.decideOpen(r, { ok: false, message: "lsof timed out" }, world).kind, "blocked");
  assert.equal(L.decideOpen(r, { ok: true }, world).kind, "blocked");
  assert.equal(L.decideOpen(r, null, world).kind, "blocked");
  const unresolved = L.decideOpen(r, ok([{ address: "t9", agent: "codex", session_id: null }]), world);
  assert.equal(unresolved.kind, "blocked");
  assert.match(unresolved.message, /t9/);
  // Another agent's unknown terminal doesn't block a Codex resume.
  assert.equal(L.decideOpen(r, ok([{ address: "t1", agent: "claude", session_id: null }]), world).kind, "resume");
});

test("decideOpen refuses when a terminal it asked about is missing from the answer", () => {
  const r = { key: "k", kind: "session", agent: "claude", session_id: "S", resumable: true };
  const plan = L.decideOpen(r, ok([{ address: "t1", agent: "claude", session_id: "X" }]), world, ["t1", "t2"]);
  assert.equal(plan.kind, "blocked");
  assert.match(plan.message, /t2/);
  assert.equal(L.decideOpen(r, ok([{ address: "t1", agent: "claude", session_id: "X" }]), world, ["t1"]).kind, "resume");
});

test("decideOpen: an unidentified agent row is focused only while an agent still runs there", () => {
  const shellOnly = { ...world, terminals: world.terminals.map((t) => (t.address === "t1" ? { ...t, program: { key: "shell", shell: true }, report: null } : t)), agents: world.agents.filter((a) => a.address !== "t1") };
  assert.equal(L.decideOpen({ kind: "live", running: { address: "t1" } }, ok([]), shellOnly).kind, "blocked");
  assert.equal(L.decideOpen({ kind: "live", running: { address: "t1" } }, ok([]), world).kind, "focus");
});

test("decideOpen: holder that can't be focused, sub-agent, gone terminal, not resumable", () => {
  const r = { key: "k", kind: "session", agent: "claude", session_id: "S", resumable: true };
  assert.equal(L.decideOpen(r, ok([{ address: "t404", agent: "claude", session_id: "S" }]), world).kind, "blocked");
  assert.deepEqual(L.decideOpen({ ...r, agent: "codex" }, ok([{ address: "t9", agent: "codex", session_id: "S" }]), world).steps, [["agent.focus", { terminal: "t9" }]]);
  assert.equal(L.decideOpen({ kind: "live", running: { address: "t404" } }, ok([]), world).kind, "blocked");
  assert.equal(L.decideOpen({ kind: "live", running: { address: "t9" } }, ok([]), world).kind, "focus");
  assert.equal(L.decideOpen({ ...r, resumable: false, why_not: "없음" }, ok([]), world).message, "없음");
  assert.equal(L.decideOpen(null, ok([]), world).kind, "blocked");
});

test("resumeSpace prefers where it last ran, then its folder, never another machine", () => {
  assert.equal(L.resumeSpace({ last_space_id: "spB", cwd: "/w/a" }, world), "spB");
  assert.equal(L.resumeSpace({ last_space_id: "gone", cwd: "/w/a/" }, world), "spA");
  assert.equal(L.resumeSpace({ cwd: "/srv" }, world), null);
  assert.equal(L.resumeSpace({ cwd: "/nowhere" }, world), null);
});

test("resumeArgv uses the person's launcher", () => {
  const known = [{ key: "codex", run: ["codex", "--no-daemon"], installed: true }, { key: "claude", run: ["my-claude"], installed: true }];
  assert.deepEqual(L.resumeArgv({ agent: "codex", resume_args: ["resume", "id", "-C", "/w"] }, known), ["codex", "--no-daemon", "resume", "id", "-C", "/w"]);
  assert.deepEqual(L.resumeArgv({ agent: "claude", resume_args: ["--resume", "id"] }, known), ["my-claude", "--resume", "id"]);
  assert.deepEqual(L.resumeArgv({ agent: "claude", resume_args: ["--resume", "id"] }, []), ["claude", "--resume", "id"]);
  assert.deepEqual(L.resumeArgv({ agent: "claude", resume_args: ["--resume", "id"] }, [{ key: "claude", run: ["x"], installed: false }]), ["claude", "--resume", "id"]);
});

test("listItems: sections without a query, flat with one; selection skips headers", () => {
  const results = [{ key: "a", running: { address: "t1" } }, { key: "b" }, { key: "c" }];
  const items = L.listItems(results, { query: "", sort: "auto" });
  assert.deepEqual(items.map((i) => i.key), ["h-running", "a", "h-recent", "b", "c"]);
  assert.equal(L.firstRow(items), 1);
  assert.equal(L.moveSelection(items, 1, 1), 3);
  assert.equal(L.moveSelection(items, 3, -1), 1);
  assert.equal(L.moveSelection(items, 4, 8), 4);
  assert.deepEqual(L.listItems(results, { query: "x", sort: "auto" }).map((i) => i.key), ["a", "b", "c"]);
  assert.deepEqual(L.listItems(results, { query: "", sort: "oldest" }).map((i) => i.key), ["a", "b", "c"]);
  assert.equal(L.moveSelection([], 0, 1), -1);
});

test("snippet rows are taller only when the title doesn't already show every word", () => {
  const seg = { segments: [["x", true]] };
  assert.equal(L.itemHeight({ kind: "row", r: { snippet: seg, title_has_all: false } }), L.ROW_SNIPPET_H);
  assert.equal(L.itemHeight({ kind: "row", r: { snippet: seg, title_has_all: true } }), L.ROW_H);
  assert.equal(L.itemHeight({ kind: "head" }), L.HEAD_H);
});

test("menuOptions and wrapWords", () => {
  const opts = L.menuOptions("project", { projects: [["acme-web", 3], ["acme-app", 1]] });
  assert.deepEqual(opts.map((o) => o.value), [null, "acme-web", "acme-app"]);
  assert.deepEqual(L.wrapWords([["a b ", false], ["프로필", true], [" c", false]]), [["a", false], ["b", false], ["프로필", true], ["c", false]]);
});

test("fromHex decodes UTF-8", () => {
  const hex = Buffer.from("프로필 수정 ok").toString("hex");
  assert.equal(L.fromHex(hex), "프로필 수정 ok");
});

test("tabName clips long titles", () => {
  assert.equal(L.tabName({ title: "짧은 제목" }), "짧은 제목");
  assert.equal(L.tabName({ title: "x".repeat(50) }).length, 36);
  assert.equal(L.tabName({ title: "" }), undefined);
});

test("a sub-agent is placed in its parent's tab, not where its labels point", () => {
  const w = {
    ...world,
    terminals: [
      ...world.terminals,
      { address: "t20", state: "live", pid: 1, parent: "t1", foreground: { pid: 2, argv: ["codex"] }, program: { key: "codex", agent: true }, report: { app: "codex" }, labels: { "herdr.space": "spB", "herdr.tab": "tbB" } },
    ],
    agents: [...world.agents, { address: "t20", tab: "tbB", space: "spB", space_name: "same", tab_name: "Claude Lead", status: "working", app: "codex" }],
  };
  const sub = L.liveTerminals(w).find((t) => t.address === "t20");
  assert.equal(sub.tab_id, "tbA");
  assert.equal(sub.space_id, "spA");
  assert.equal(sub.parent, "t1");
});
