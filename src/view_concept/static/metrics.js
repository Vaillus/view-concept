/* view-concept — the Metrics tab of a branch review (the metrics report).

   The tab draws GET /api/s/<slug>/metrics (metrics.py): the review's clock (pickup, agent
   and user time, its runs on lanes), where agent time goes by role, the waiting per batch,
   the runs list, the side-thread turns, then every branch review of the repository
   compared by variant. Each number opens onto the one under it, in the detail panel: a
   batch onto the runs of its coordinator pass, a role onto its runs, a run onto its
   activity bar and measures (a stretch of the bar shows, on hover, the command that ended
   it), a role agent that started helpers onto its wave.

   Two kinds of time are drawn as a hatched break of fixed width instead of to scale:
   user time over a minute (a clock span with "break") and a stalled run stretch (over
   ten minutes, "stalled"), which the server already leaves out of every sum.

   app.js shows the tab on branch reviews only and calls refreshMetrics() when the tab is
   shown and on each state update while it is. The published page has no Metrics tab. */

"use strict";

(() => {
  const CUT = 25; // seconds a hatched break is drawn as
  // Activity name (metrics.py) -> its colour class, in legend order.
  const ACTS = [["loading context", "a-load"], ["exploring code", "a-explore"], ["writing", "a-write"],
    ["view-concept commands", "a-commands"], ["launch time", "a-launch"], ["waiting on helpers", "a-helpers"],
    ["report", "a-report"], ["other", "a-other"]];
  const actClass = (a) => (ACTS.find(([n]) => n === a) || ACTS[ACTS.length - 1])[1];
  const LANES = ["coordinator", "planner", "writer", "writer helpers", "implementer", "implementer helpers",
    "reviewer", "reviewer helpers"];
  const QUALITY = [["comments", "comments"], ["rewrites", "rewrites"], ["unclear", "unclear answers"],
    ["changes_after_approval", "changes after approval"], ["findings", "findings"]];
  const ROLES = ["planner", "writer", "implementer", "reviewer"];

  let data = null;        // last payload, null before the first fetch or on a 404
  let missing = "";       // why there is no payload
  let sel = null;         // { kind: "run" | "batch" | "role", id }
  let sort = { k: "start", dir: 1 };
  let sub = "runs";       // "runs" | "turns"
  let inflight = false, again = false;

  /* ---------------- small helpers ---------------- */

  function h(tag, cls, text, attrs = {}) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    for (const [k, v] of Object.entries(attrs)) {
      if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (k === "style") Object.assign(n.style, v);
      else if (v != null && v !== false) n.setAttribute(k, v);
    }
    return n;
  }
  const add = (parent, ...kids) => { for (const k of kids) if (k != null) parent.append(k); return parent; };
  const ms = (iso) => Date.parse(iso);
  function dur(s) {
    if (s == null) return "—";
    s = Math.round(s);
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
    return `${Math.floor(s / 3600)} h ${String(Math.floor(s / 60) % 60).padStart(2, "0")} min`;
  }
  const clk = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour12: false }) : "—");
  const kilo = (n) => (n == null ? "—" : n >= 1000 ? `${Math.round(n / 1000)} k` : String(n));
  const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
  const sum = (xs) => xs.reduce((a, b) => a + (b || 0), 0);
  const chip = (text, cls = "", tip) => h("span", `mx-chip ${cls}`, text, { "data-tip": tip });
  const label = (text) => h("div", "mx-label", text);

  const runsById = () => Object.fromEntries((data.runs || []).map((r) => [r.id, r]));
  const laneOf = (r) => (r.kind === "pass" ? "coordinator" : r.role + (r.kind === "helper" ? " helpers" : ""));
  function runName(r) {
    if (r.kind === "helper") return `helper · ${r.section || r.description || r.id.slice(0, 8)}`;
    if (r.kind === "pass") return `pass · ${r.trigger}`;
    return r.trigger || r.description || r.id.slice(0, 8);
  }
  function parentName(r, byId) {
    if (!r.parent) return "none";
    if (r.parent.startsWith("pass:")) return `coordinator pass on ${r.parent.slice(5)}`;
    const p = byId[r.parent];
    return p ? `${p.role} run on ${p.trigger}` : r.parent.slice(0, 8);
  }
  function batchLabel(b) {
    return b ? `${b.id} · ${b.label}` : "";
  }

  /* ---------------- fetching ---------------- */

  async function refreshMetrics() {
    if (inflight) { again = true; return; }
    inflight = true;
    try {
      const r = await fetch(`/api/s/${SLUG}/metrics`);
      if (r.ok) { data = await r.json(); missing = ""; }
      else { data = null; missing = r.status === 404 ? "No metrics for this session." : `Could not load the metrics (${r.status}).`; }
    } catch (e) {
      data = null;
      missing = "Could not reach the server.";
    } finally {
      inflight = false;
    }
    draw();
    if (again) { again = false; refreshMetrics(); }
  }
  window.refreshMetrics = refreshMetrics;

  /* ---------------- the tab ---------------- */

  function draw() {
    const root = document.getElementById("metrics");
    if (!root) return;
    const scroll = root.scrollTop;
    if (!data) {
      root.replaceChildren(h("p", "mx-empty dim", missing || "Loading the metrics…"));
      return;
    }
    const inner = h("div", "mx");
    add(inner, head(), clockPart(), h("div", "mx-panel mx-detail", null, { id: "mx-detail" }),
      add(h("div", "mx-grid"), rolesPart(), batchesPart()), listsPart(), comparePart());
    root.replaceChildren(inner);
    if (sel && !selectionExists()) sel = null;
    if (!sel) {
      const last = [...(data.runs || [])].filter((r) => r.kind === "role").pop();
      if (last) sel = { kind: "run", id: last.id };
    }
    detail();
    root.scrollTop = scroll;
  }

  function selectionExists() {
    if (sel.kind === "run") return (data.runs || []).some((r) => r.id === sel.id);
    if (sel.kind === "batch") return (data.batches || []).some((b) => b.id === sel.id);
    return (data.by_role || []).some((x) => x.role === sel.id);
  }
  function select(kind, id) {
    sel = { kind, id };
    detail();
    document.getElementById("mx-detail").scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  /* The review's totals: your waiting split, the stalled time, the counts. */
  function head() {
    const part = h("div", "mx-part");
    const v = data.variant || { name: "none", models: {} };
    const models = Object.entries(v.models || {}).map(([role, m]) => `${role} on ${m}`).join(", ");
    add(part, label(`this review · ${data.slug} · variant ${v.name}${models ? ` (${models})` : ""}${data.model ? ` · ${data.model}` : ""}`));
    const clock = data.clock || [];
    const pickup = sum(clock.filter((c) => c.kind === "pickup").map((c) => c.seconds));
    const stalled = sum(stallCuts().map(([a, b]) => b - a));
    const agent = Math.max(0, sum(clock.filter((c) => c.kind === "agent").map((c) => c.seconds)) - stalled);
    const user = sum(clock.filter((c) => c.kind === "user").map((c) => c.seconds));
    const runs = data.runs || [];
    const kpis = h("div", "mx-kpis");
    for (const [k, val, tip] of [
      ["your waiting", dur(pickup + agent), "pickup time + agent time, stalls left out"],
      ["pickup time", dur(pickup), "from sending a batch to the coordinator acting on it"],
      ["agent time", dur(agent), "from the coordinator acting on a batch to the page waiting for you again"],
      ["stalled", dur(stalled), "run stretches over ten minutes, left out of every sum"],
      ["user time", dur(user), "from the page waiting for you to your next batch"],
      ["runs", `${runs.filter((r) => r.kind === "role").length} + ${runs.filter((r) => r.kind === "helper").length} helpers`],
      ["coordinator passes", String(runs.filter((r) => r.kind === "pass").length || (data.batches || []).filter((b) => !b.busy).length)],
      ["thread turns", String((data.threads || []).length)],
    ]) add(kpis, add(h("div", "mx-kpi", null, { "data-tip": tip }), h("span", "mx-label", k), h("b", "", val)));
    const q = data.quality || {};
    const signals = h("div", "mx-chips");
    for (const [k, name] of QUALITY) add(signals, chip(`${name} ${q[k] ?? 0}`));
    add(signals, chip(`reviewer runs after the first ${q.reviewer_reruns ?? 0}`, "",
      "each one a round of fixes: the points the reviewer flagged and the implementer fixed"));
    add(part, kpis, signals);
    if (!runs.length) {
      add(part, h("p", "mx-note dim", data.agent && data.agent !== "claude"
        ? `This session was driven by ${data.agent === "command" ? "Jazz" : data.agent}: only Claude Code keeps transcripts to read, so it lists no runs. Its waiting split and quality signals come from the session's own files.`
        : "No run found in the session's transcripts yet."));
    }
    return part;
  }

  /* ---------------- the review's clock ----------------
     Times are seconds from the clock's first moment. A break (user time over a minute, a
     stalled stretch) is drawn CUT seconds wide; X maps a time to a percentage of the axis. */

  function origin() {
    const starts = [...(data.clock || []).map((c) => ms(c.start)), ...(data.runs || []).map((r) => ms(r.start))];
    return starts.length ? Math.min(...starts) : 0;
  }
  const rel = (iso, t0) => (ms(iso) - t0) / 1000;

  // Stalled stretches of every run, as absolute [start, end] ms, merged where they overlap.
  function stallCuts() {
    const cuts = [];
    for (const r of data.runs || []) {
      for (const s of r.stretches || []) if (s.stalled) cuts.push([ms(r.start) / 1000 + s.start, ms(r.start) / 1000 + s.end]);
    }
    return merge(cuts);
  }
  function merge(cuts) {
    cuts.sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const c of cuts) {
      const last = out[out.length - 1];
      if (last && c[0] <= last[1]) { last[1] = Math.max(last[1], c[1]); if (c[2] === "stall") last[2] = "stall"; }
      else out.push([...c]);
    }
    return out;
  }

  function axis() {
    const t0 = origin();
    const ends = [...(data.clock || []).map((c) => ms(c.end)), ...(data.runs || []).map((r) => ms(r.end))];
    const end = ends.length ? (Math.max(...ends) - t0) / 1000 : 0;
    const userCuts = (data.clock || []).filter((c) => c.kind === "user" && c.break)
      .map((c) => [rel(c.start, t0), rel(c.end, t0), "user"]);
    const stalls = stallCuts().map(([a, b]) => [a - t0 / 1000, b - t0 / 1000, "stall"]);
    const cuts = merge([...userCuts, ...stalls]);
    const span = Math.max(1, end - sum(cuts.map(([a, b]) => b - a)) + cuts.length * CUT);
    const X = (t) => {
      let x = t;
      for (const [a, b] of cuts) {
        if (t >= b) x -= (b - a) - CUT;
        else if (t > a) { x -= (t - a) - (CUT * (t - a)) / (b - a); break; }
      }
      return (100 * x) / span;
    };
    return { t0, end, cuts, X };
  }

  function place(n, X, a, b) {
    n.style.left = `${X(a)}%`;
    n.style.width = `${Math.max(0.15, X(b) - X(a))}%`;
    return n;
  }

  function clockPart() {
    const part = add(h("div", "mx-part"), label("the review's clock · user time and stalls drawn as hatched breaks"));
    if (!(data.clock || []).length && !(data.runs || []).length) return add(part, h("p", "dim", "No batch yet."));
    const { t0, cuts, X } = axis();
    const tl = h("div", "mx-tl");
    // The page band: pickup and agent time per batch, the batches sent as ticks.
    const band = h("div", "mx-band");
    for (const c of data.clock || []) {
      if (c.kind === "user") continue;
      const tip = `${c.batch || ""} ${c.kind === "pickup" ? "pickup time" : "agent time"} ${dur(c.seconds)} · ${clk(c.start)} → ${clk(c.end)}`;
      add(band, place(h("div", `mx-seg ${c.kind === "pickup" ? "p-pick" : "p-agent"}`, null, { "data-tip": tip }),
        X, rel(c.start, t0), rel(c.end, t0)));
    }
    for (const [a, b, k] of cuts) {
      const tip = `${k === "stall" ? "stalled" : "user time"} ${dur(b - a)} · ${clk(new Date(t0 + a * 1000).toISOString())} → ${clk(new Date(t0 + b * 1000).toISOString())}`;
      add(band, place(h("div", `mx-seg cut${k === "stall" ? " stall" : ""}`, null, { "data-tip": tip }), X, a, b));
    }
    for (const b of data.batches || []) {
      const tick = h("button", "mx-tick", null, { "data-tip": `${batchLabel(b)} · sent ${clk(b.sent)}`, onclick: () => select("batch", b.id) });
      tick.style.left = `${X(rel(b.sent, t0))}%`;
      add(band, tick);
    }
    add(tl, add(h("div", "mx-lane"), h("div", "mx-who", "page"), band));
    // One lane per role (helpers on their own), runs packed in rows so none overlap.
    const runs = data.runs || [];
    const names = [...LANES, ...new Set(runs.map(laneOf).filter((n) => !LANES.includes(n)))];
    for (const name of names) {
      const rs = runs.filter((r) => laneOf(r) === name).sort((a, b) => ms(a.start) - ms(b.start));
      if (!rs.length) continue;
      const track = h("div", "mx-track");
      const rows = [];
      for (const r of rs) {
        const a = rel(r.start, t0), b = rel(r.end, t0);
        let i = rows.findIndex((e) => e < a);
        if (i < 0) { i = rows.length; rows.push(0); add(track, h("div", "mx-row")); }
        rows[i] = b;
        const row = track.children[i];
        for (const s of r.stretches || []) {
          add(row, place(h("div", `mx-seg ${s.stalled ? "cut stall" : actClass(s.activity)}`), X, a + s.start, a + s.end));
        }
        const box = h("button", "mx-runbox", null, {
          "data-run": r.id,
          "data-tip": `${r.role} · ${runName(r)} · ${dur(r.wall)}${r.stalled ? ` + ${dur(r.stalled)} stalled` : ""}`,
          onclick: () => select("run", r.id),
        });
        add(row, place(box, X, a, b));
      }
      add(tl, add(h("div", "mx-lane"), h("div", "mx-who", name), track));
    }
    // Long breaks get their length written under the axis.
    const ax = h("div", "mx-axis");
    let last = -99;
    for (const [a, b, k] of cuts) {
      if (b - a < 1200) continue;
      const c = (X(a) + X(b)) / 2;
      if (c - last < 9) continue;
      last = c;
      add(ax, h("span", "", `${k === "stall" ? "stall " : ""}${dur(b - a).replace(/ \d+ s$/, "")}`, { style: { left: `${c}%` } }));
    }
    add(tl, add(h("div", "mx-lane"), h("div"), ax));
    return add(part, tl, legend());
  }

  function legend() {
    const lg = h("div", "mx-legend");
    if ((data.runs || []).length) for (const [name, cls] of ACTS) add(lg, add(h("span"), h("i", `mx-sw ${cls}`), name));
    for (const [name, cls] of [["pickup time", "p-pick"], ["agent time", "p-agent"], ["user time", "cut"], ["stalled", "cut stall"]]) {
      add(lg, add(h("span"), h("i", `mx-sw ${cls}`), name));
    }
    return lg;
  }

  /* ---------------- the detail panel ---------------- */

  function detail() {
    const box = document.getElementById("mx-detail");
    if (!box) return;
    document.querySelectorAll("#metrics .sel").forEach((n) => n.classList.remove("sel"));
    if (!sel) {
      box.replaceChildren(h("p", "dim", "Click a batch, a role or a run."));
      return;
    }
    const mark = (q) => document.querySelectorAll(`#metrics ${q}`).forEach((n) => n.classList.add("sel"));
    if (sel.kind === "run") {
      mark(`[data-run="${sel.id}"]`);
      box.replaceChildren(...runDetail(runsById()[sel.id]));
    } else if (sel.kind === "batch") {
      mark(`[data-batch="${sel.id}"]`);
      box.replaceChildren(...batchDetail((data.batches || []).find((b) => b.id === sel.id)));
    } else {
      mark(`[data-role="${sel.id}"]`);
      box.replaceChildren(...roleDetail(sel.id));
    }
  }

  // A small table of runs, each row opening the run.
  function runList(runs) {
    const t = h("table", "mx-table");
    add(t, add(h("thead"), add(h("tr"), ...["run", "role", "start", "wall", "startup", "API calls"]
      .map((k, i) => h("th", i > 2 ? "mx-num" : "", k)))));
    const tb = h("tbody");
    for (const r of runs) {
      add(tb, add(h("tr", "", null, { "data-run": r.id, onclick: () => select("run", r.id) }),
        h("td", r.kind === "helper" ? "mx-ind" : "", runName(r)), h("td", "", r.role), h("td", "", clk(r.start)),
        h("td", "mx-num", dur(r.wall) + (r.stalled ? " + stall" : "")),
        h("td", "mx-num", r.first_write == null ? "no write" : dur((r.startup || {}).seconds)),
        h("td", "mx-num", String(r.api_calls ?? "—"))));
    }
    return add(t, tb);
  }

  function batchDetail(b) {
    if (!b) return [h("p", "dim", "This batch is gone.")];
    const byId = runsById();
    const runs = (b.runs || []).map((id) => byId[id]).filter(Boolean);
    const out = [add(h("div", "mx-dhead"), h("span", "mx-label", "batch"), h("b", "", batchLabel(b)),
      h("span", "dim", `sent ${clk(b.sent)}${b.delivered ? ` · delivered ${clk(b.delivered)}` : ""}`))];
    const chips = h("div", "mx-chips");
    if (b.busy) add(chips, chip(`sent during a run · waited ${dur(b.agent)}`, "", "its wait counts as agent time: the page was not waiting for you"));
    else add(chips, chip(`pickup ${dur(b.pickup)}`), chip(`agent ${dur(b.agent)}`));
    if (b.stalled) add(chips, chip("holds a stall", "mx-flag"));
    if (b.user != null) add(chips, chip(`then user time ${dur(b.user)}`));
    out.push(chips);
    out.push(runs.length ? add(h("div", "mx-sub"), label("the runs of its coordinator pass"), runList(runs))
      : h("p", "dim", "No run recorded for this batch."));
    return out;
  }

  function roleDetail(role) {
    const x = (data.by_role || []).find((r) => r.role === role) || { activities: {} };
    const runs = (data.runs || []).filter((r) => r.role === role).sort((a, b) => ms(a.start) - ms(b.start));
    return [add(h("div", "mx-dhead"), h("span", "mx-label", "role"), h("b", "", role),
      h("span", "dim", `${x.runs ?? runs.length} runs · ${dur(x.seconds)} of agent time, stalls left out`)),
    activityTable(x.activities || {}), add(h("div", "mx-sub"), label("its runs"), runList(runs))];
  }

  function activityTable(acts) {
    const entries = Object.entries(acts).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...entries.map(([, v]) => v));
    const g = h("div", "mx-acts");
    for (const [k, v] of entries) {
      add(g, h("span", "", k), h("div", `mx-abar-one ${actClass(k)}`, null, { style: { width: `${(100 * v) / max}%` } }),
        h("span", "mx-num", dur(v)));
    }
    return add(h("div", "mx-tile wide"), h("span", "mx-label", "time by activity"), g);
  }

  // A run's activity bar: each stretch as wide as it lasted, a stalled one CUT seconds wide.
  function activityBar(r, from = 0, marker = true) {
    const bar = h("div", "mx-abar");
    const st = (r.stretches || []).filter((s) => s.end > from).map((s) => ({ ...s, start: Math.max(s.start, from) }));
    const w = (s) => (s.stalled ? CUT : s.end - s.start);
    const total = Math.max(0.001, sum(st.map(w)));
    for (const s of st) {
      const tip = `${s.activity} · ${Math.round(s.start)}–${Math.round(s.end)} s${s.tool ? ` · ${s.tool}` : ""}${s.command ? `: ${s.command}` : ""}${s.tool_seconds != null ? ` · the tool ran ${s.tool_seconds} s` : ""}${s.stalled ? " · stalled" : ""}`;
      add(bar, h("div", s.stalled ? "cut stall" : actClass(s.activity), null, { "data-tip": tip, style: { width: `${(100 * w(s)) / total}%` } }));
    }
    if (marker && r.first_write != null) {
      let x = 0;
      for (const s of st) {
        if (s.start >= r.first_write) break;
        x += s.stalled ? CUT : Math.min(s.end, r.first_write) - s.start;
      }
      add(bar, h("div", "mx-first", null, { "data-tip": `first write at ${Math.round(r.first_write)} s`, style: { left: `${(100 * x) / total}%` } }));
    }
    return { bar, total };
  }

  function runDetail(r) {
    if (!r) return [h("p", "dim", "This run is gone.")];
    const byId = runsById();
    const kind = { role: "role agent run", helper: "helper", pass: "coordinator pass" }[r.kind] || r.kind;
    const out = [add(h("div", "mx-dhead"), h("span", "mx-label", kind), h("b", "", `${r.role} · ${runName(r)}`),
      h("span", "dim", `${clk(r.start)} → ${clk(r.end)}`))];
    const ident = add(h("div", "mx-chips"), chip(`role ${r.role}`), chip(`trigger ${r.trigger || "—"}`));
    const parent = chip(`parent ${parentName(r, byId)}`, byId[r.parent] ? "mx-link" : "");
    if (byId[r.parent]) parent.addEventListener("click", () => select("run", r.parent));
    add(ident, parent, chip(r.model || "model unknown"), chip(`variant ${r.variant || "none"}`));
    if (r.section) add(ident, chip(`section ${r.section}`));
    const flags = r.flags || {};
    if (flags.slow) add(ident, chip("over 3 × its role's median", "mx-flag", medianTip(r)));
    if (flags.series) add(ident, seriesChip(flags.series));
    out.push(ident, activityBar(r).bar);
    const startup = r.startup || {};
    const tk = r.tokens || {};
    const ctx = r.context || {};
    const tiles = h("div", "mx-tiles");
    for (const [k, v, tip] of [
      ["wall time", dur(r.wall) + (r.stalled ? ` + ${dur(r.stalled)} stalled` : ""), "first message to last, stalled stretches left out"],
      ["startup cost", r.first_write == null ? "no write" : `${dur(startup.seconds)} · ${startup.api_calls} calls · ${kilo(startup.prompt_tokens)} tokens`, "what the run spent before its first write"],
      ["model time", `${dur(r.model_time)} of ${dur(r.wall)}`, `tools ran ${dur(r.tool_time)}`],
      ["calls", `${r.api_calls} API · ${r.tool_calls} tool`],
      ["prompt tokens", `${kilo(tk.total)} · ${kilo(tk.first)} → ${kilo(tk.last)} per call · ${pct(tk.cache_read_share)} cached`],
      ["output tokens", tk.output == null ? "not recorded" : `${kilo(tk.output)} over ${tk.output_calls} calls`, "only the calls that record why they stopped carry the final count"],
      ["context size", `${kilo(ctx.prompt_tokens)} tokens + ${kilo(ctx.read_chars)} characters`, ctx.context_chars != null ? `${kilo(ctx.context_chars)} characters from the context command` : null],
    ]) add(tiles, add(h("div", "mx-tile", null, { "data-tip": tip }), h("span", "mx-label", k), h("b", "", v)));
    add(tiles, activityTable(r.activities || {}));
    out.push(tiles);
    const wave = (data.waves || []).find((w) => w.run === r.id);
    if (wave) out.push(waveView(wave, byId));
    else if (r.kind === "helper" && r.wave != null && data.waves[r.wave]) {
      const w = data.waves[r.wave];
      out.push(add(h("div", "mx-chips"), chip(`one of ${w.helpers.length} helpers of a wave · open its ${w.role} run`, "mx-link", null)));
      out[out.length - 1].firstChild.addEventListener("click", () => select("run", w.run));
    }
    return out;
  }

  function medianTip(r) {
    const m = (data.medians || {})[r.role];
    return m == null ? null : `${r.role} median over the repository's reviews: ${dur(m)}`;
  }
  function seriesChip(id) {
    const s = (data.series || []).find((x) => x.id === id);
    return chip(`series ${id}`, "mx-series",
      s ? `${s.runs.length} ${s.role} runs in a row, each on one event · startups summed ${dur(s.startup)}` : null);
  }

  // A wave: the role agent and its helpers on one axis from its launch.
  function waveView(w, byId) {
    const box = add(h("div", "mx-wave"), label(`wave · ${w.helpers.length} helpers · from the launch`));
    const owner = byId[w.run];
    const a = ms(w.start) / 1000 - (w.launch || 0) - 2;
    const members = [owner, ...w.helpers.map((id) => byId[id])].filter(Boolean);
    const b = Math.max(...members.map((r) => ms(r.end) / 1000));
    const W = Math.max(1, b - a);
    for (const r of members) {
      const from = Math.max(0, a - ms(r.start) / 1000);
      const { bar } = activityBar(r, from, false);
      const off = ms(r.start) / 1000 + from;
      bar.style.position = "absolute";
      bar.style.left = `${(100 * (off - a)) / W}%`;
      bar.style.width = `${(100 * (ms(r.end) / 1000 - off)) / W}%`;
      const name = r === owner ? r.role : (r.section || runName(r));
      add(box, add(h("div", "mx-wrow", null, { "data-run": r.id, onclick: () => select("run", r.id) }),
        h("span", "dim", name), add(h("div", "mx-wtrack"), bar),
        h("span", "mx-num", r === owner ? dur(b - a) : dur(r.wall))));
    }
    const slow = byId[w.slowest_helper];
    add(box, add(h("div", "mx-chips"), chip(`launch ${dur(w.launch)}`, "", "from the role agent's last action before the wave to its helpers' start"),
      chip(`slowest ${dur(w.slowest)}${slow ? ` (${slow.section || runName(slow)})` : ""}`), chip(`sum ${dur(w.sum)}`),
      chip(`sum − slowest − launch ${dur(w.saved)}`), chip(`loading per helper ${dur((w.loading || [])[0])}–${dur((w.loading || [])[1])}`)));
    return box;
  }

  /* ---------------- by role, per batch ---------------- */

  function rolesPart() {
    const part = add(h("div", "mx-part"), label("where agent time goes · by role, stalls left out"));
    const rows = (data.by_role || []).filter((x) => x.runs);
    if (!rows.length) return add(part, h("p", "dim", "No run."));
    const max = Math.max(1, ...rows.map((x) => x.seconds));
    add(part, add(h("div", "mx-rrow head"), h("span", "", "role · runs"), h("span", "", "time by activity"), h("span", "mx-num", "agent time")));
    for (const x of rows) {
      const stack = h("div", "mx-stack", null, { style: { width: `${(100 * x.seconds) / max}%` } });
      const total = Math.max(0.001, sum(Object.values(x.activities || {})));
      for (const [name, cls] of ACTS) {
        const v = (x.activities || {})[name];
        if (v) add(stack, h("div", cls, null, { "data-tip": `${name} ${dur(v)}`, style: { width: `${(100 * v) / total}%` } }));
      }
      add(part, add(h("div", "mx-rrow mx-click", null, { "data-role": x.role, onclick: () => select("role", x.role) }),
        add(h("span"), `${x.role} `, h("span", "dim", String(x.runs))), stack, h("span", "mx-num", dur(x.seconds))));
    }
    return part;
  }

  function batchesPart() {
    const part = add(h("div", "mx-part"), label("your waiting · per batch"));
    const bs = data.batches || [];
    if (!bs.length) return add(part, h("p", "dim", "No batch yet."));
    const tot = (b) => (b.busy ? b.agent || 0 : (b.pickup || 0) + (b.agent || 0));
    const max = Math.max(1, ...bs.map(tot));
    add(part, add(h("div", "mx-brow head"), h("span", "", "batch"), h("span", "", "carried"), h("span", "", "pickup · agent"), h("span", "mx-num", "waited")));
    for (const b of bs) {
      const row = h("div", "mx-brow mx-click", null, { "data-batch": b.id, onclick: () => select("batch", b.id) });
      add(row, h("span", "", b.id), h("span", "dim", b.label));
      if (b.busy) {
        add(row, h("div", "mx-joined", null, { "data-tip": "sent during a run: waited for it to end, as agent time", style: { width: `${(100 * tot(b)) / max}%` } }),
          h("span", "mx-num dim", dur(b.agent)));
      } else {
        const t = Math.max(0.001, tot(b));
        add(row, add(h("div", "mx-stack", null, { style: { width: `${Math.max(1, (100 * t) / max)}%` } }),
          h("div", "p-pick", null, { "data-tip": `pickup ${dur(b.pickup)}`, style: { width: `${(100 * (b.pickup || 0)) / t}%` } }),
          h("div", "p-agent", null, { "data-tip": `agent ${dur(b.agent)}`, style: { width: `${(100 * (b.agent || 0)) / t}%` } })),
        add(h("span", "mx-num"), dur(t), b.stalled ? h("span", "mx-flag", " + stall") : null));
      }
      add(part, row);
    }
    return part;
  }

  /* ---------------- runs list, side-thread turns ---------------- */

  // [name, sort key, numeric]: numeric columns sort descending first and align right.
  const COLS = [
    ["run", (r) => runName(r), false],
    ["marks", (r) => ((r.flags || {}).slow ? 2 : 0) + ((r.flags || {}).series ? 1 : 0), true],
    ["role", (r) => r.role, false], ["start", (r) => ms(r.start), false], ["wall", (r) => r.wall, true],
    ["startup", (r) => (r.first_write == null ? -1 : (r.startup || {}).seconds), true],
    ["model time", (r) => r.model_time, true], ["calls", (r) => r.api_calls, true],
    ["prompt tokens", (r) => (r.tokens || {}).total, true], ["cached", (r) => (r.tokens || {}).cache_read_share, true],
  ];

  function listsPart() {
    const part = h("div", "mx-part");
    const tabs = h("div", "mx-subtabs");
    for (const [k, name] of [["runs", `runs ${(data.runs || []).length}`], ["turns", `side-thread turns ${(data.threads || []).length}`]]) {
      add(tabs, h("button", `mx-subtab${sub === k ? " on" : ""}`, name, { onclick: () => { sub = k; draw(); } }));
    }
    add(part, tabs, sub === "runs" ? runsTable() : turnsTable());
    return part;
  }

  // Default order: by start, each helper under its role agent.
  function ordered(runs) {
    const byId = Object.fromEntries(runs.map((r) => [r.id, r]));
    if (sort.k !== "start") {
      const f = COLS.find(([k]) => k === sort.k)[1];
      return [...runs].sort((a, b) => sort.dir * ((f(a) > f(b)) - (f(a) < f(b))));
    }
    const key = (r) => (r.kind === "helper" && byId[r.parent] ? ms(byId[r.parent].start) + 0.5 + ms(r.start) / 1e15 : ms(r.start));
    return [...runs].sort((a, b) => sort.dir * (key(a) - key(b)));
  }

  function runsTable() {
    const runs = data.runs || [];
    if (!runs.length) return h("p", "dim", "No run.");
    const wrap = h("div", "mx-scroll");
    const t = h("table", "mx-table mx-runs");
    add(t, add(h("thead"), add(h("tr"), ...COLS.map(([k, , num]) => h("th", `mx-sort${num && k !== "marks" ? " mx-num" : ""}`,
      k + (sort.k === k ? (sort.dir > 0 ? " ↑" : " ↓") : ""), {
        onclick: () => { sort = { k, dir: sort.k === k ? -sort.dir : (num ? -1 : 1) }; draw(); },
      })))));
    const tb = h("tbody");
    for (const r of ordered(runs)) {
      const flags = r.flags || {};
      const marks = h("td");
      if (flags.slow) add(marks, chip("slow", "mx-flag", medianTip(r) ? `over 3 × the ${medianTip(r)}` : "over 3 × its role's median"));
      if (flags.series) add(marks, seriesChip(flags.series));
      const tk = r.tokens || {};
      add(tb, add(h("tr", "", null, { "data-run": r.id, onclick: () => select("run", r.id) }),
        h("td", r.kind === "helper" && sort.k === "start" ? "mx-ind" : "", runName(r)), marks,
        h("td", "", r.role), h("td", "", clk(r.start)),
        h("td", "mx-num", dur(r.wall) + (r.stalled ? " + stall" : "")),
        h("td", "mx-num", r.first_write == null ? "—" : dur((r.startup || {}).seconds)),
        h("td", "mx-num", dur(r.model_time)), h("td", "mx-num", String(r.api_calls ?? "—")),
        h("td", "mx-num", kilo(tk.total)), h("td", "mx-num", pct(tk.cache_read_share))));
    }
    add(wrap, add(t, tb));
    for (const s of data.series || []) {
      add(wrap, h("p", "mx-note dim", `series ${s.id} · ${s.runs.length} ${s.role} runs in a row, each on one event: ${s.runs.length} startups, ${dur(s.startup)} in all, what one continued run would save.`));
    }
    return wrap;
  }

  function turnsTable() {
    const turns = data.threads || [];
    if (!turns.length) return h("p", "dim", "No side-thread turn.");
    const t = h("table", "mx-table");
    add(t, add(h("thead"), add(h("tr"), ...["thread", "turn", "section", "start", "first text", "wall time", "prompt tokens", "tool calls"]
      .map((k, i) => h("th", i > 3 ? "mx-num" : "", k)))));
    const tb = h("tbody");
    for (const x of turns) {
      add(tb, add(h("tr"), h("td", "", x.thread), h("td", "", `${x.turn}${x.turn === 1 ? " · new session" : ""}`),
        h("td", "", x.section || "—"), h("td", "", clk(x.start)),
        h("td", "mx-num", x.first_text == null ? "—" : `${x.first_text} s`), h("td", "mx-num", x.end == null ? "—" : `${x.end} s`),
        h("td", "mx-num", kilo(x.prompt_tokens)), h("td", "mx-num", x.tool_calls == null ? "—" : String(x.tool_calls))));
    }
    return add(h("div", "mx-scroll"), add(t, tb));
  }

  /* ---------------- every branch review of the repository, by variant ---------------- */

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = 10 ** Math.floor(Math.log10(v));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  function comparePart() {
    const part = add(h("div", "mx-part"), label("every branch review of this repository, by variant · one point per review"));
    const variants = ((data.compare || {}).variants || []);
    if (!variants.length) return add(part, h("p", "dim", "No branch review to compare."));
    const lg = h("div", "mx-legend");
    variants.forEach((v, i) => add(lg, add(h("span", `mx-v${i % 6}`), h("i", v.reviews.length ? "mx-sw mx-dotsw" : "mx-ring"),
      `${v.name} · ${v.reviews.length ? `${v.reviews.length} review${v.reviews.length > 1 ? "s" : ""}` : "no review yet"}`)));
    add(lg, add(h("span"), h("i", "mx-sw mx-medsw"), "the variant's median"), add(h("span"), h("i", "mx-sw mx-dotsw mx-mesw"), "this review"));
    const roles = [...new Set(variants.flatMap((v) => v.reviews.flatMap((r) => Object.keys(r.roles || {}))))]
      .sort((a, b) => (ROLES.indexOf(a) + 1 || 99) - (ROLES.indexOf(b) + 1 || 99));
    const grid = add(h("div", "mx-grid"),
      strips("median run wall time, per role", roles, variants, (r, k) => (r.roles || {})[k], (m, k) => (m.roles || {})[k], " s"),
      strips("quality signals, per review", QUALITY.map(([k]) => k), variants, (r, k) => (r.quality || {})[k], (m, k) => (m.quality || {})[k], "",
        Object.fromEntries(QUALITY)));
    return add(part, lg, grid);
  }

  function strips(title, keys, variants, value, median, unit, names = {}) {
    const box = add(h("div", "mx-rows"), label(title));
    const max = niceMax(Math.max(1, ...keys.flatMap((k) => variants.flatMap((v) => v.reviews.map((r) => value(r, k) ?? 0)))));
    for (const k of keys) {
      const track = h("div", "mx-strack");
      variants.forEach((v, i) => {
        for (const r of v.reviews) {
          const x = value(r, k);
          if (x == null) continue;
          add(track, h("div", `mx-dot mx-v${i % 6}${r.current ? " me" : ""}`, null,
            { "data-tip": `${r.slug} · ${v.name} · ${unit ? dur(x) : x}`, style: { left: `${(100 * Math.min(x, max)) / max}%` } }));
        }
        const m = median(v.median || {}, k);
        if (m != null) {
          add(track, h("div", `mx-med mx-v${i % 6}`, null,
            { "data-tip": `${v.name} · median ${unit ? dur(m) : m}`, style: { left: `${(100 * Math.min(m, max)) / max}%` } }));
        }
      });
      add(box, add(h("div", "mx-strip"), h("span", "dim", names[k] || k), track));
    }
    const ax = h("div", "mx-sax");
    for (let i = 0; i <= 4; i++) {
      const v = (max * i) / 4;
      add(ax, h("span", "", `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`, { style: { left: `${i * 25}%` } }));
    }
    add(box, add(h("div", "mx-strip"), h("span"), ax));
    return box;
  }
})();
