// Session Spotlight: one search box over every Claude Code and Codex session on
// this computer, running or ended. Cmd+K opens it as a centered dialog.
// Type to search titles, conversations, projects and folders; ↑/↓ choose,
// Enter goes to the terminal that runs the session (by its exact address) or
// resumes an ended one in its own folder; Tab walks the filter chips; Esc closes.
//
// The searching happens in engine/spotlight.py (Python stdlib + SQLite FTS5),
// which this view runs with exec(). Nothing leaves the machine.

import { View, div, svg, image } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, v_virtual_list, VirtualListScrollHandle, ScrollHandle, Popup } from "gpui-base";
import {
  exec, run, notify, theme, props, closeOverlay, settings, spaces, panes, agents, terminals,
  knownAgents, appHome, checking, nextCommand,
} from "herdr";
import * as L from "./lib.js";

const MOD = "session-spotlight";
const ICON = (name) => `mods/${MOD}/icons/${name}.svg`;
const CONTEXT = "SessionSpotlight";
const NEXT_FILTER = "session_spotlight_next_filter";
const PREV_FILTER = "session_spotlight_prev_filter";
const CHIP_ICON = { date: "calendar", project: "folder", agent: "bot", status: "status", sort: "sort" };
const HEADER_H = 56;
const FILTERS_H = 40;
const FOOTER_H = 34;

// Shared by every copy of this build, so the next open paints the last answer at once.
const cache = { results: null, facets: null, total: 0, resolved: {}, index: null, resumedAt: {}, language: null };

function tint(color, alpha) {
  return typeof color === "string" && color.length === 7 ? color + alpha : color;
}

function unzoomed(size) {
  const zoom = Number(settings()?.zoom) || 1;
  return { width: size.width / zoom, height: size.height / zoom };
}

export default class SessionSpotlight extends View {
  init(_props, cx) {
    this.enginePath = `${appHome()}/mods/${MOD}/engine/spotlight.py`;
    this.query = "";
    this.filters = { ...L.DEFAULT_FILTERS };
    this.data = cache.results ? { ok: true, results: cache.results, facets: cache.facets, total: cache.total, query: {}, took_ms: null, cached: true } : null;
    this.items = this.data ? L.listItems(this.data.results, { query: "", sort: "auto" }) : [];
    this.sel = L.firstRow(this.items);
    this.selKey = this.sel >= 0 ? this.items[this.sel].key : null;
    this.seq = 0;
    this.typed = 0;
    this.pending = 0;
    this.indexing = false;
    this.indexInfo = cache.index;
    this.previews = new Map();
    this.preview = null;
    this.previewFor = null;
    this.menu = null;
    this.menuAt = 0;
    this.flash = null;
    this.error = null;
    this.resuming = null;
    this.size = { width: 920, height: 4000 };
    this.live = [];
    this.liveFp = "";
    this.listScroll = VirtualListScrollHandle.new();
    this.previewScroll = ScrollHandle.new();
    this.handle = cx.focus_handle();
    if (cache.language) L.setLanguage(cache.language);
    // The placeholder is drawn by render (see header), so it follows the language setting.
    this.input = InputState.new({ placeholder: "" });
    this.input.on("change", (_e, cx) => this.onQuery(cx));
    this.input.on("submit", (_e, cx) => this.onSubmit(cx));
    this.input.focus();
    cx.timer.after(150, () => this.input.focus());
    cx.bind_keys([
      { keystroke: "tab", action: NEXT_FILTER, context: CONTEXT },
      { keystroke: "shift-tab", action: PREV_FILTER, context: CONTEXT },
    ]);
    if (checking()) return;
    this.refreshLive(cx, true);
    this.runIndex(cx);
    // Herdr's terminals change while the dialog is open (an agent starts or ends).
    cx.timer.every(4000, (cx) => this.refreshLive(cx, false));
    // `herdr-app do session-spotlight.<command>` drives the dialog for scripted checks.
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand();
        this.command(c, cx);
        cx.notify();
      }
    });
  }

  // -- language ---------------------------------------------------------------

  // The engine reads the config ("language": "en" | "ko" | "auto") and answers with "en" or "ko"
  // on every search, so the dialog and the engine always agree on which config file counts.
  applyLanguage(lang) {
    if (!lang || lang === L.language()) return false;
    L.setLanguage(lang);
    cache.language = L.language();
    return true;
  }

  // -- engine ---------------------------------------------------------------

  async call(args, timeout = 20000) {
    // -I -S: no site packages or PYTHON* variables (faster start, nothing from outside the engine).
    const r = await exec("python3", ["-B", "-I", "-S", this.enginePath, ...args], { timeout });
    let data = null;
    try {
      data = JSON.parse(r.stdout);
    } catch {}
    if (!data) {
      const why = (r.stderr || r.stdout || "").trim().split("\n").filter(Boolean).pop();
      throw new Error(why || (r.code ? L.t("engine_exit", { code: r.code }) : L.t("engine_no_answer")));
    }
    return data;
  }

  world() {
    return { terminals: terminals(), agents: agents(), panes: panes(), spaces: spaces() };
  }

  refreshLive(cx, first) {
    const live = L.liveTerminals(this.world());
    const fp = L.liveFingerprint(live) + "|" + live.map((t) => `${t.status}:${t.space_name}:${t.tab_name}`).join(",");
    this.live = live;
    if (!first && fp === this.liveFp) return;
    this.liveFp = fp;
    if (first) this.search(cx);
    const seq = (this.resolveSeq = (this.resolveSeq ?? 0) + 1);
    cx.spawn(async (cx) => {
      try {
        const res = await this.call(["resolve", `--terminals=${JSON.stringify(L.resolveInput(live))}`], 10000);
        if (seq !== this.resolveSeq) return; // a newer answer is coming: never let an older one win
        const map = {};
        for (const t of res.terminals ?? []) map[t.address] = t;
        cache.resolved = map;
      } catch (e) {
        if (seq !== this.resolveSeq) return;
        this.error = L.t("resolve_failed", { error: e?.message ?? e });
      }
      this.search(cx);
    });
  }

  runIndex(cx) {
    this.indexing = true;
    cx.spawn(async (cx) => {
      try {
        const r = await this.call(["index"], 600000);
        if (r.ok === false) throw new Error(r.message || r.error);
        if (r.status === "done") {
          this.indexInfo = r;
          cache.index = r;
          if (r.reread || r.appended || r.removed || r.excluded) {
            this.previews.clear(); // conversations may have grown
            this.search(cx);
          }
        }
      } catch (e) {
        this.error = L.t("index_failed", { error: e?.message ?? e });
      }
      this.indexing = false;
      cx.notify();
    });
  }

  search(cx) {
    const seq = ++this.seq;
    const queryAtStart = this.query;
    const args = L.searchArgs(this.query, this.filters, JSON.stringify(L.liveForSearch(this.live, cache.resolved)));
    this.pending++;
    cx.spawn(async (cx) => {
      let data = null;
      let err = null;
      try {
        data = await this.call(args);
      } catch (e) {
        err = e;
      }
      this.pending--;
      if (seq !== this.seq) return cx.notify(); // a newer search is on its way
      if (err || !data?.ok) {
        this.error = err ? `${err.message ?? err}` : data?.message || L.t("search_failed");
        return cx.notify();
      }
      this.error = null;
      this.applyLanguage(data.language);
      this.apply(data, queryAtStart !== this.lastQuery, cx);
      this.lastQuery = queryAtStart;
      if (!this.query && JSON.stringify(this.filters) === JSON.stringify(L.DEFAULT_FILTERS)) {
        cache.results = data.results;
        cache.facets = data.facets;
        cache.total = data.total;
      }
      cx.notify();
    });
  }

  apply(data, reset, cx) {
    this.data = data;
    this.items = L.listItems(data.results, { query: this.query, sort: this.filters.sort });
    let at = reset ? -1 : this.items.findIndex((it) => it.kind === "row" && it.key === this.selKey);
    if (at < 0) at = L.firstRow(this.items);
    this.previewFor = null; // the query or the row may have changed what the preview shows
    this.select(at, reset, cx);
  }

  select(at, scroll = true, cx = null) {
    this.sel = at;
    const it = this.items[at];
    this.selKey = it?.kind === "row" ? it.key : null;
    if (scroll && at >= 0) this.listScroll.scroll_to_item(at);
    if (cx && this.size.width >= 700) this.ensurePreview(cx, this.current());
  }

  current() {
    const it = this.items[this.sel];
    return it?.kind === "row" ? it.r : null;
  }

  // -- preview --------------------------------------------------------------

  ensurePreview(cx, r) {
    if (!r || r.kind === "live") {
      this.preview = null;
      this.previewFor = r?.key ?? null;
      return;
    }
    const id = `${r.key}|${this.query}|${r.snippet?.message_id ?? ""}`;
    if (this.previewFor === id) return;
    this.previewFor = id;
    const hit = this.previews.get(id);
    if (hit) {
      this.preview = hit;
      this.scrollPreview(hit);
      return;
    }
    this.preview = { loading: true, key: r.key };
    const args = ["preview", `--key=${r.key}`, `--query=${this.query}`];
    if (r.snippet?.message_id) args.push("--message", String(r.snippet.message_id));
    // Let fast arrowing settle before reading.
    cx.timer.after(70, (cx) => {
      if (this.previewFor !== id) return;
      cx.spawn(async (cx) => {
        let p;
        try {
          p = await this.call(args, 10000);
        } catch (e) {
          p = { ok: false, message: `${e?.message ?? e}` };
        }
        p.key = r.key; // errors too, so the pane shows them instead of "loading"
        if (this.previews.size > 60) this.previews.clear();
        this.previews.set(id, p);
        if (this.previewFor !== id) return;
        this.preview = p;
        this.scrollPreview(p);
        cx.notify();
      });
    });
  }

  scrollPreview(p) {
    if (!p?.messages?.length) return;
    const at = p.messages.findIndex((m) => m.match);
    this.previewScroll.scroll_to_item(at >= 0 ? at : p.messages.length - 1);
  }

  // -- input ----------------------------------------------------------------

  onQuery(cx) {
    this.query = this.input.value();
    this.flash = null;
    const n = ++this.typed;
    cx.timer.after(60, (cx) => {
      if (n === this.typed) this.search(cx);
    });
    cx.notify();
  }

  onSubmit(cx) {
    if (this.menu) return this.chooseMenu(this.menuAt, cx);
    this.open(cx);
  }

  move(step, cx) {
    const at = L.moveSelection(this.items, this.sel, step);
    if (at >= 0) this.select(at, true, cx);
  }

  // Scripted checks: `herdr-app do session-spotlight.<command>` while the dialog is open.
  // down, up, open, close, menu-<kind>, query-<utf8 hex>, select-<address|session id|key>, filter-<kind>-<value|default>.
  command(c, cx) {
    const text = String(c);
    const dash = text.indexOf("-");
    const name = dash < 0 ? text : text.slice(0, dash);
    const value = dash < 0 ? "" : text.slice(dash + 1);
    if (name === "down") this.move(1, cx);
    else if (name === "up") this.move(-1, cx);
    else if (name === "open") this.open(cx);
    else if (name === "close") this.close();
    else if (name === "menu") this.toggleMenu(value);
    else if (name === "query") {
      const q = L.fromHex(value);
      this.input.set_value(q);
      this.query = q;
      this.search(cx);
    } else if (name === "select") {
      const at = this.items.findIndex((it) => it.kind === "row" && (it.key === value || it.r.session_id === value || it.r.running?.address === value));
      if (at >= 0) this.select(at, true, cx);
    } else if (name === "filter") {
      const [kind, ...rest] = value.split("-");
      const v = rest.join("-");
      if (kind in this.filters) this.setFilter(kind, v === "default" ? L.DEFAULT_FILTERS[kind] : kind === "project" ? L.fromHex(v) : v, cx);
    }
  }

  // -- filters --------------------------------------------------------------

  setFilter(kind, value, cx) {
    this.filters = { ...this.filters, [kind]: value };
    this.lastQuery = null; // selection starts over
    this.search(cx);
  }

  toggleMenu(kind) {
    if (this.menu === kind) {
      this.menu = null;
      return;
    }
    this.menu = kind;
    const opts = L.menuOptions(kind, this.data?.facets);
    const now = this.filters[kind];
    this.menuAt = Math.max(0, opts.findIndex((o) => o.value === now));
  }

  stepMenu(dir) {
    const i = L.FILTER_KINDS.indexOf(this.menu);
    const next = i < 0 ? (dir > 0 ? 0 : L.FILTER_KINDS.length - 1) : (i + dir + L.FILTER_KINDS.length) % L.FILTER_KINDS.length;
    if (i >= 0 && ((dir > 0 && i === L.FILTER_KINDS.length - 1) || (dir < 0 && i === 0))) {
      this.menu = null; // past the last chip: back to the results
      return;
    }
    this.toggleMenu(L.FILTER_KINDS[next]);
  }

  chooseMenu(index, cx) {
    const kind = this.menu;
    const opt = L.menuOptions(kind, this.data?.facets)[index];
    this.menu = null;
    if (!opt) return;
    if (kind === "date" && opt.value === "custom") {
      const { text, select } = L.customRangeQuery(this.query);
      this.input.set_value(text);
      this.input.set_selected_range({ start: select[0], end: select[1] });
      this.query = text;
      this.filters = { ...this.filters, date: "all" };
      this.input.focus();
      this.search(cx);
      return;
    }
    this.setFilter(kind, opt.value, cx);
    this.input.focus();
  }

  resetFilters(cx) {
    this.filters = { ...L.DEFAULT_FILTERS };
    this.search(cx);
  }

  // -- open / resume ---------------------------------------------------------

  close() {
    closeOverlay(props().overlay);
  }

  // Enter: where does the session run right now? Asked fresh every time, so a stale list
  // never focuses the wrong terminal or starts a second copy of a running session.
  open(cx) {
    const r = this.current();
    if (!r) return;
    if (this.resuming) return;
    this.resuming = r.key;
    this.flash = null;
    cx.notify();
    cx.spawn(async (cx) => {
      const live = L.liveTerminals(this.world());
      const asked = L.resolveInput(live);
      let resolved;
      try {
        resolved = await this.call(["resolve", `--terminals=${JSON.stringify(asked)}`, "--no-remember"], 10000);
      } catch (e) {
        resolved = { ok: false, message: `${e?.message ?? e}` };
      }
      const plan = L.decideOpen(r, resolved, this.world(), asked.map((t) => t.address));
      if (plan.kind === "blocked") return this.fail(plan.message, cx);
      if (plan.kind === "focus") {
        for (const [name, args] of plan.steps) run(name, args);
        this.resuming = null;
        if (!r.running || r.running.address !== plan.address) {
          notify({ title: "Session Spotlight", body: L.t("moved_to_holder", { address: plan.address }), level: "info" });
        }
        return this.close();
      }
      await this.resume(r, cx, L.liveFingerprint(live));
    });
  }

  fail(text, cx) {
    this.resuming = null;
    this.flash = { level: "error", text };
    cx.notify();
  }

  // Starts an ended session, after `open` confirmed no terminal runs it.
  async resume(r, cx, fingerprint) {
    // A session started a moment ago may not have written its pid file yet: don't start it twice.
    const recent = cache.resumedAt[r.key];
    if (recent && Date.now() - recent < 15000) {
      return this.fail(L.t("just_resumed"), cx);
    }
    let check;
    try {
      check = await this.call(["check", `--key=${r.key}`], 10000);
    } catch (e) {
      return this.fail(L.t("check_failed", { error: e?.message ?? e }), cx);
    }
    if (!check.ok) {
      this.runIndex(cx); // the history file is gone: let the index catch up
      return this.fail(L.reason(check.error, null, check.message) || L.t("err_not_found"), cx);
    }
    if (!check.resumable) {
      if (!check.source_exists) this.runIndex(cx); // gone from disk: drop it from the list too
      return this.fail(L.whyNot(check) || L.t("open_cannot_resume"), cx);
    }
    let known = [];
    try {
      known = await knownAgents();
    } catch {}
    const argv = L.resumeArgv({ ...r, resume_args: check.resume_args }, known);
    // Terminals that appeared or changed while this was checking weren't part of the answer.
    if (L.liveFingerprint(L.liveTerminals(this.world())) !== fingerprint) {
      return this.fail(L.t("terminals_changed"), cx);
    }
    const space = L.resumeSpace(r, this.world());
    const name = L.tabName(r);
    cache.resumedAt[r.key] = Date.now();
    if (space) run("tab.new", { space, folder: check.cwd, argv, ...(name ? { name } : {}) });
    else run("space.new", { folder: check.cwd, argv, ...(name ? { tab: name } : {}) });
    this.resuming = null;
    this.close();
    notify({ title: L.t("resumed_title"), body: `${r.title}\n${argv.join(" ")}`, level: "success", timeout: 5000 });
  }

  // -- drawing ----------------------------------------------------------------

  agentIcon(r, size, t) {
    if (r.agent === "claude") return image("icons/claude.svg").size(size).flex_none().rounded(5);
    if (r.agent === "codex") return image("icons/codex.svg").size(size).flex_none().rounded(5);
    return h_flex().size(size).flex_none().items_center().justify_center().rounded(5).bg(t.hover).child(svg(ICON("terminal")).size(size * 0.7).text_color(t.muted));
  }

  statusPill(status, t) {
    const s = L.statusLabel(status);
    // Idle reads quietly (no tinted pill): open in a terminal, doing nothing.
    if (s.tone === "idle") {
      return h_flex().flex_none().h(18).px(7).gap(5).items_center().rounded(9).bg(t.hover)
        .child(div().size(6).rounded(3).bg(t.idle ?? t.dim))
        .child(div().text_size(10.5).text_color(t.muted).child(s.label));
    }
    const color = t[s.tone] ?? t.accent;
    return h_flex().flex_none().h(18).px(7).gap(5).items_center().rounded(9).bg(tint(color, "1f"))
      .child(s.spin ? svg(ICON("spinner")).size(9).text_color(color).spin(900) : div().size(6).rounded(3).bg(color))
      .child(div().text_size(10.5).font_medium().text_color(color).child(s.label));
  }

  segs(segments, color, hit, opts = {}) {
    return h_flex().min_w(0).overflow_hidden().whitespace_nowrap().children(
      (segments ?? []).map(([text, on]) =>
        div().flex_none().text_color(on ? hit : color).when(on, (d) => d.font_semibold()).when(Boolean(opts.weight) && !on, (d) => d.font_weight(opts.weight)).child(text),
      ),
    );
  }

  row(it, selected, t, nowMs) {
    if (it.kind === "head") {
      return h_flex().h(L.HEAD_H).px(18).pt(8).gap(6).items_center().text_size(11).font_semibold().text_color(t.dim)
        .child(L.t(it.labelKey)).child(div().font_medium().text_color(t.dim).child(String(it.count)));
    }
    const r = it.r;
    const snippet = L.showsSnippet(r);
    const where = r.space_name || r.project || "~";
    const meta = [where, r.agent_name, L.formatWhen(r.updated_at, nowMs)].filter(Boolean).join(" · ");
    return v_flex().h(snippet ? L.ROW_SNIPPET_H : L.ROW_H).px(6).justify_center().child(
      v_flex().h_full().px(10).gap(3).justify_center().rounded(9)
        .when(selected, (el) => el.bg(t.selected))
        .when(!selected, (el) => el.hover((s) => s.bg(t.hover)))
        .child(
          h_flex().gap(10).items_center().min_w(0)
            .child(this.agentIcon(r, 20, t))
            .child(div().flex_1().min_w(0).text_size(13.5).text_color(t.foreground).child(
              r.title_segments?.some(([, on]) => on)
                ? this.segs(r.title_segments, t.foreground, t.accent, { weight: selected ? 600 : 500 })
                : div().truncate().font_weight(selected ? 600 : 500).child(r.title || L.t("untitled")),
            ))
            .when(Boolean(r.running), (el) => el.child(this.statusPill(r.running.status, t)))
            .when(!r.running && r.archived, (el) => el.child(div().flex_none().text_size(10.5).text_color(t.dim).child(L.t("archived")))),
        )
        .child(h_flex().pl(30).min_w(0).text_size(12).text_color(t.dim).child(div().truncate().child(meta)))
        .when(snippet, (el) =>
          el.child(h_flex().pl(30).min_w(0).text_size(12).text_color(t.muted)
            .child(div().flex_none().text_color(t.dim).pr(6).child(r.snippet.role === "user" ? L.t("snippet_you") : L.t("snippet_agent")))
            .child(this.segs(r.snippet.segments, t.muted, t.accent)))),
    );
  }

  chips(t) {
    const parsed = this.data?.query ?? {};
    return h_flex().h(FILTERS_H).flex_none().px(14).gap(6).items_center().children(
      L.FILTER_KINDS.map((kind) => {
        const active = L.chipActive(kind, this.filters, parsed);
        const open = this.menu === kind;
        const chip = h_flex()
          .id(`chip-${kind}`)
          .h(26)
          .px(9)
          .gap(6)
          .flex_none()
          .items_center()
          .rounded(7)
          .cursor_pointer()
          .text_size(12)
          .text_color(active ? t.accent : t.muted)
          .when(active && !open, (el) => el.bg(tint(t.accent, "1a")))
          .when(open, (el) => el.bg(t.hover).text_color(t.foreground))
          .hover((s) => s.bg(t.hover).text_color(t.foreground))
          .on_click((_e, cx) => {
            this.toggleMenu(kind);
            cx.notify();
          })
          .child(svg(ICON(CHIP_ICON[kind])).size(13).flex_none())
          .child(div().child(L.chipLabel(kind, this.filters, parsed)))
          .child(svg(ICON("chevron-down")).size(11).flex_none().text_color(t.dim));
        // The menu is painted in a layer above the dialog, pinned under its chip.
        return Popup.new(`chip-menu-${kind}`, chip).anchor("top_left").when(open, (el) => el.content(this.menuPanel(t, kind)));
      }),
    )
      .child(div().flex_1())
      .when(L.FILTER_KINDS.some((k) => L.chipActive(k, this.filters, {})), (el) =>
        el.child(div().id("chip-reset").px(8).h(26).flex().items_center().rounded(7).text_size(11.5).text_color(t.dim).cursor_pointer()
          .hover((s) => s.bg(t.hover).text_color(t.foreground))
          .on_click((_e, cx) => this.resetFilters(cx))
          .child(L.t("clear_filters"))));
  }

  menuPanel(t, kind) {
    const opts = L.menuOptions(kind, this.data?.facets);
    const current = this.filters[kind];
    const width = kind === "project" ? 260 : 200;
    const maxH = Math.min(320, Math.max(120, this.size.height - HEADER_H - FILTERS_H - 40));
    const height = Math.min(maxH, opts.length * 30 + 8);
    return v_flex()
      .id(`spotlight-menu-${kind}`)
      .mt(4)
      .w(width)
      .h(height)
      .p(4)
      .rounded(10)
      .bg(t.popover)
      .border_1()
      .border_color(t.border)
      .shadow_lg()
      .overflow_y_scrollbar()
      .on_mouse_down_out((_e, cx) => {
        if (this.menu !== kind) return;
        this.menu = null;
        cx.notify();
      })
      .children(opts.map((o, i) =>
        h_flex()
          .id(`menu-${i}`)
          .h(30)
          .flex_none()
          .px(8)
          .gap(8)
          .items_center()
          .rounded(6)
          .cursor_pointer()
          .text_size(12.5)
          .text_color(t.foreground)
          .when(i === this.menuAt, (el) => el.bg(t.selected))
          .hover((s) => s.bg(t.hover))
          .on_click((_e, cx) => {
            this.chooseMenu(i, cx);
            cx.notify();
          })
          .child(div().w(14).flex_none().child(o.value === current ? svg(ICON("check")).size(13).text_color(t.accent) : ""))
          .child(div().flex_1().min_w(0).truncate().child(o.label))
          .when(o.count != null, (el) => el.child(div().flex_none().text_size(11).text_color(t.dim).child(String(o.count))))));
  }

  previewPane(t, r, height, nowMs) {
    const pane = v_flex().flex_1().min_w(0).h(height).px(20).py(16).gap(14).overflow_hidden();
    if (!r) {
      return pane.items_center().justify_center().child(div().text_color(t.dim).text_size(12.5).child(L.t("preview_empty")));
    }
    const p = this.preview && this.preview.key === r.key ? this.preview : null;
    const metaRow = (label, value, mono) =>
      h_flex().gap(10).min_w(0).items_center().text_size(12)
        .child(div().w(72).flex_none().text_color(t.dim).child(label))
        .child(div().flex_1().min_w(0).truncate().text_color(t.muted).when(Boolean(mono), (d) => d.font_family(settings().font_family ?? "JetBrains Mono").text_size(11.5)).child(value || "—"));
    const where = r.running ? `${r.running.space_name || "?"} › ${r.running.tab_name || "?"}` : r.space_name || r.project || "~";

    let action;
    if (r.running) {
      action = { icon: "arrow-up-right", color: t.accent, text: L.t("action_focus", { where, address: r.running.address }) };
    } else if (r.kind === "live") {
      action = { icon: "terminal", color: t.dim, text: L.t("action_gone") };
    } else if (r.resumable) {
      const cmd = r.agent === "claude" ? `claude --resume ${r.session_id.slice(0, 8)}…` : `codex resume ${r.session_id.slice(0, 8)}…`;
      action = { icon: "history", color: t.accent, text: L.t("action_resume", { command: cmd }) };
    } else {
      action = { icon: "status", color: t.blocked, text: L.t("action_blocked", { why: L.whyNot(r) }) };
    }
    if (this.resuming === r.key) action = { icon: "spinner", color: t.accent, text: L.t("action_preparing"), spin: true };

    pane
      .child(
        h_flex().gap(12).items_start().min_w(0)
          .child(this.agentIcon(r, 26, t))
          .child(
            v_flex().flex_1().min_w(0).gap(4)
              .child(div().text_size(15.5).line_height("22px").max_h(44).overflow_hidden().font_semibold().text_color(t.foreground).child(r.title || L.t("untitled")))
              .child(h_flex().gap(8).items_center().text_size(12).text_color(t.dim)
                .when(Boolean(r.running), (el) => el.child(this.statusPill(r.running.status, t)))
                .when(!r.running, (el) => el.child(div().child(L.t("ended"))))
                .child(div().child("·")).child(div().child(r.agent_name))),
          ),
      )
      .child(
        v_flex().gap(5).flex_none()
          .child(metaRow(r.running ? L.t("meta_space") : L.t("meta_project"), where))
          .child(metaRow(L.t("meta_folder"), r.cwd ? r.cwd.replace(/^\/Users\/[^/]+/, "~") : "", true))
          .when(Boolean(r.branch), (el) => el.child(metaRow(L.t("meta_branch"), r.branch, true)))
          .child(metaRow(L.t("meta_started"), L.formatFull(r.created_at)))
          .child(metaRow(L.t("meta_last_active"), `${L.formatFull(r.updated_at)}  (${L.formatRelative(r.updated_at, nowMs)})`))
          .when(r.kind !== "live", (el) => el.child(metaRow(L.t("meta_messages"), L.t("meta_messages_count", { n: r.messages }))))
          .when(Boolean(r.session_id), (el) => el.child(metaRow(L.t("meta_session_id"), r.session_id, true))),
      )
      .child(
        h_flex().flex_none().h(32).px(10).gap(8).items_center().rounded(8).bg(tint(action.color, "14"))
          .child(action.spin ? svg(ICON("spinner")).size(13).text_color(action.color).spin(900) : svg(ICON(action.icon)).size(13).flex_none().text_color(action.color))
          .child(div().flex_1().min_w(0).truncate().text_size(12).text_color(action.color === t.blocked ? t.blocked : t.foreground).child(action.text)),
      );

    if (r.kind === "live") {
      return pane.child(div().text_size(12).text_color(t.dim).child(
        r.session_id ? L.t("live_unindexed") : L.t("live_unknown"),
      ));
    }
    const head = h_flex().flex_none().items_center().gap(8).text_size(11).font_semibold().text_color(t.dim)
      .child(div().child(this.query.trim() ? L.t("conversation_matched") : L.t("conversation_recent")))
      .when(Boolean(p?.messages?.length), (el) =>
        el.child(div().font_medium().child(`${p.first_index + 1}–${p.first_index + p.messages.length} / ${p.message_count}`)));
    pane.child(div().h(1).flex_none().bg(t.border)).child(head);
    if (!p || p.loading) return pane.child(h_flex().gap(8).items_center().text_size(12).text_color(t.dim).child(svg(ICON("spinner")).size(12).spin(900)).child(L.t("loading")));
    if (!p.ok) return pane.child(div().text_size(12).text_color(t.blocked).child(L.reason(p.error, null, p.message) || L.t("preview_failed")));
    if (!p.messages.length) return pane.child(div().text_size(12).text_color(t.dim).child(L.t("no_messages")));
    return pane.child(
      v_flex().id("spotlight-conversation").flex_1().min_h(0).gap(12).pr(6).overflow_y_scrollbar().track_scroll(this.previewScroll).children(
        p.messages.map((m, i) => {
          const me = m.role === "user";
          const body = m.match
            ? h_flex().flex_wrap().gap(4).children(L.wrapWords(m.segments, 500).map(([w, on], j) =>
                div().id(`w-${i}-${j}`).h(19).line_height("19px").text_color(on ? t.foreground : t.muted).when(on, (d) => d.px(3).rounded(4).bg(tint(t.accent, "40"))).child(w)))
            : div().text_color(t.muted).line_height("19px").child(m.text);
          return v_flex().gap(4).px(10).py(8).rounded(8)
            .when(me, (el) => el.bg(t.hover))
            .when(m.match, (el) => el.border_1().border_color(tint(t.accent, "99")))
            .child(h_flex().gap(8).items_center().text_size(11).child(div().font_semibold().text_color(me ? t.foreground : t.accent).child(me ? L.t("snippet_you") : r.agent_name)).child(div().text_color(t.dim).child(L.formatWhen(m.ts, nowMs))))
            .child(div().text_size(12.5).child(body));
        }),
      ),
    );
  }

  notice(t) {
    const typed = this.query.trim();
    if (this.error && !this.data) return { text: this.error, color: t.blocked };
    if (!this.data) return { text: L.t("loading_sessions"), color: t.dim, spin: true };
    if (this.data.index && !this.data.index.ready) return { text: L.t("first_index"), color: t.dim, spin: true };
    if (typed) return { text: L.t("no_match", { query: typed }), sub: L.t("no_match_hint"), color: t.dim };
    return { text: L.t("no_sessions"), sub: L.t("no_sessions_hint"), color: t.dim };
  }

  render(cx) {
    const t = theme();
    const nowMs = Date.now();
    const narrow = this.size.width < 700;
    const bodyH = Math.max(120, Math.min(this.size.height, 4000) - HEADER_H - FILTERS_H - FOOTER_H - 2);
    const listW = narrow ? this.size.width : Math.round(Math.max(360, Math.min(500, this.size.width * 0.48)));
    const items = this.items;
    const r = this.current();
    const busy = this.pending > 0 || this.indexing || Boolean(this.resuming);

    const key = (cap, label) =>
      h_flex().gap(5).items_center()
        .child(div().px(5).h(17).flex().items_center().rounded(4).bg(t.hover).text_size(10.5).text_color(t.muted).child(cap))
        .child(div().text_color(t.dim).child(label));

    let status;
    if (this.flash) status = div().max_w(460).truncate().text_color(this.flash.level === "error" ? t.blocked : t.done).child(this.flash.text);
    else if (this.error && this.data) status = div().max_w(460).truncate().text_color(t.blocked).child(this.error);
    else if (this.data) {
      const parts = [this.data.total === 1 ? L.t("count_sessions_one") : L.t("count_sessions", { n: this.data.total })];
      if (this.data.took_ms != null) parts.push(`${Math.round(this.data.took_ms)}ms`);
      if (this.indexing) parts.push(L.t("updating_index"));
      status = div().text_color(t.dim).child(parts.join(" · "));
    } else status = div();

    const list = items.length
      ? v_flex().relative().w(listW).h(bodyH).flex_none().py(4).child(
          v_virtual_list("spotlight-rows", items.length, items.map(L.itemHeight), (i) => items[i].key, (range) => {
            const out = [];
            for (let i = range.start; i < range.end; i++) out.push(this.row(items[i], i === this.sel, t, nowMs));
            return out;
          })
            .w_full()
            .h(bodyH - 8)
            .track_scroll(this.listScroll)
            .on_item_click((key, cx) => {
              const at = this.items.findIndex((it) => it.key === key);
              if (at < 0 || this.items[at].kind !== "row") return;
              if (at === this.sel) this.open(cx);
              else this.select(at, false, cx);
              this.input.focus();
              cx.notify();
            }),
        )
      : (() => {
          const n = this.notice(t);
          return v_flex().w(listW).h(bodyH).flex_none().items_center().justify_center().gap(6).px(32)
            .child(h_flex().gap(8).items_center()
              .when(Boolean(n.spin), (el) => el.child(svg(ICON("spinner")).size(13).text_color(t.dim).spin(900)))
              .child(div().text_size(13).text_color(n.color).text_center().child(n.text)))
            .when(Boolean(n.sub), (el) => el.child(div().text_size(12).text_color(t.dim).text_center().child(n.sub)))
            .when(L.FILTER_KINDS.some((k) => L.chipActive(k, this.filters, {})), (el) =>
              el.child(div().id("empty-reset").mt(6).px(10).py(5).rounded(7).bg(t.hover).text_size(12).text_color(t.foreground).cursor_pointer()
                .on_click((_e, cx) => this.resetFilters(cx)).child(L.t("clear_filters"))));
        })();

    return v_flex()
      .id("session-spotlight")
      .key_context(CONTEXT)
      .on_action(NEXT_FILTER, (_e, cx) => {
        this.stepMenu(1);
        cx.notify();
      })
      .on_action(PREV_FILTER, (_e, cx) => {
        this.stepMenu(-1);
        cx.notify();
      })
      .track_focus(this.handle)
      .size_full()
      .relative()
      .on_size_change((size, cx) => {
        const s = unzoomed(size);
        if (Math.abs(s.width - this.size.width) > 0.5 || Math.abs(s.height - this.size.height) > 0.5) {
          this.size = s;
          cx.notify();
        }
      })
      .bg(t.popover)
      .text_size(13)
      .on_key_down((e, cx) => {
        const k = e.key;
        if (k === "escape") {
          if (this.menu) this.menu = null;
          else return this.close();
        } else if (this.menu) {
          const n = L.menuOptions(this.menu, this.data?.facets).length;
          if (k === "down") this.menuAt = Math.min(n - 1, this.menuAt + 1);
          else if (k === "up") this.menuAt = Math.max(0, this.menuAt - 1);
          else if (k === "left") this.stepMenu(-1);
          else if (k === "right") this.stepMenu(1);
          else return;
        } else if (k === "down") this.move(1, cx);
        else if (k === "up") this.move(-1, cx);
        else if (k === "pagedown") this.move(8, cx);
        else if (k === "pageup") this.move(-8, cx);
        else return;
        cx.stop_propagation();
        cx.notify();
      })
      .child(
        h_flex().h(HEADER_H).flex_none().px(18).gap(12).items_center()
          .child(svg(ICON("search")).size(18).flex_none().text_color(t.dim))
          .child(
            div().relative().flex_1().h_full().min_w(0)
              .when(!this.query, (el) => el.child(
                h_flex().absolute().inset_0().items_center().text_size(16).text_color(t.dim).child(div().truncate().child(L.t("placeholder")))))
              .child(Input.new(this.input).size_full().text_size(16).text_color(t.foreground)),
          )
          .when(busy, (el) => el.child(svg(ICON("spinner")).size(14).flex_none().text_color(t.dim).spin(900)))
          .child(div().id("spotlight-esc").flex_none().px(6).h(20).flex().items_center().rounded(5).text_size(11).text_color(t.dim).cursor_pointer()
            .hover((s) => s.bg(t.hover).text_color(t.foreground)).on_click(() => this.close()).child("esc")),
      )
      .child(this.chips(t))
      .child(div().h(1).flex_none().bg(t.border))
      .child(
        h_flex().h(bodyH).flex_none().min_h(0)
          .child(list)
          .when(!narrow, (el) => el.child(div().w(1).h_full().flex_none().bg(t.border)).child(this.previewPane(t, r, bodyH, nowMs))),
      )
      .child(div().h(1).flex_none().bg(t.border))
      .child(
        h_flex().h(FOOTER_H).flex_none().px(16).gap(14).items_center().text_size(11)
          .child(key("↑↓", L.t("key_select")))
          .child(key("↵", r?.running ? L.t("key_go") : r && r.kind !== "live" ? L.t("key_resume") : L.t("key_open")))
          .child(key("⇥", L.t("key_filters")))
          .child(key("esc", L.t("key_close")))
          .child(div().flex_1())
          .child(status),
      )
  }
}
