/* view-concept — the session page.

   Tabs share the main space: in a feature whose scoper draws the problem, the scoping tab
   (the drawing and its holes, see "the scoping tab"), the plan (the scope block with the agent questions, outline,
   lexicon, change history), the explanation (one block per explanation section; the Model
   tab of a feature), in a feature that has reached the refactoring step the
   code tab (the refactor sections, the refactoring part), and once a doc set exists the
   Doc tab (the repo docs the branch concerns, see "the Doc tab"); the review pane (a conversation: sent batches and answered agent
   questions, a line counting the open ones, then the draft comments) stays on the
   right. The page never edits the explanation: the agent writes the files, the server
   streams "changed", the page re-fetches. The page writes batches of comments, and side
   threads: separate read-only agent conversations run by the server, streamed through
   "threads" events. A thread shows in a popover on its passage (see "side threads"
   below).

   A comment is anchored by (section id, quoted text, a few characters of prefix). The
   quote is searched again after every re-render, so an anchor survives edits elsewhere
   in the section and silently disappears when its passage is rewritten. */

"use strict";

const SLUG = decodeURIComponent(location.pathname.split("/").pop());
// Where a browser kept its drafts and note before the drafts file (see "drafts"): moved
// to the session folder the first time this browser opens the session.
const DRAFTS_KEY = `view-concept:drafts:${SLUG}`;
const NOTE_KEY = `view-concept:note:${SLUG}`;
const POSITION_KEY = `view-concept:position:${SLUG}`; // the saved position (see "saved position")
const WIDTH_KEY = "view-concept:review-width"; // per browser, for every session
const THREAD_SIZE_KEY = "view-concept:thread-size"; // the same: {width, height} of a thread

let state = null;        // last payload from /api/s/<slug>
let planChanged = false;
let drafts = [];          // the drafts file's drafts (see "drafts"), the box being typed in kept as typed
let pendingSelection = null;
let tab = null;          // "scoping" | "plan" | "model" | "refactor" | "doc" | "metrics" | "review" (narrow layout)
let lastPhase = null;
let threadsState = { forkable: true, threads: [] };
let popThread = null;          // id of the thread shown in the popover
let threadRanges = [];         // [thread, range] of every thread whose passage is found
const cards = new Map();       // thread id -> its card's DOM parts, built once

const $ = (sel, root = document) => root.querySelector(sel);

function loadJSON(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
}
function saveJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode */ }
}
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(c);
  return n;
}
function toast(msg, ms = 3000) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}
const collapse = (s) => s.replace(/\s+/g, " ").trim();
// A draft is sent when it has text, or when it carries a thread: the thread is the comment.
const ready = (d) => d.text.trim() || d.thread;

/* ---------------- data ---------------- */

async function load() {
  const r = await fetch(`/api/s/${SLUG}`);
  if (!r.ok) {
    $("#model").replaceChildren(el("p", { class: "error", text: `Could not load: ${(await r.json()).detail}` }));
    return;
  }
  const next = await r.json();
  if (state && JSON.stringify(state.plan) !== JSON.stringify(next.plan)) planChanged = true;
  state = next;
  render();
  if (tab === "metrics") refreshMetrics();
}

function connect() {
  const es = new EventSource(`/api/s/${SLUG}/events`);
  const live = $("#live");
  es.addEventListener("hello", () => { live.textContent = "live"; live.className = "live on"; });
  es.addEventListener("changed", () => load());
  es.addEventListener("threads", () => loadThreads());
  es.addEventListener("drafts", () => loadDrafts());
  es.addEventListener("listening", (e) => {
    if (!state) return;
    state.listening = JSON.parse(e.data).listening;
    renderListening();
  });
  es.onerror = () => { live.textContent = "offline"; live.className = "live off"; };
}

/* ---------------- render ---------------- */

/* Every section, in outline order, then any section file the outline does not list. */
function allSections() {
  const ids = state.plan.outline.map((s) => s.id);
  const extra = Object.keys(state.sections).filter((k) => !ids.includes(k))
    .map((id) => ({ id, title: id, earns: "not in the outline" }));
  return [...state.plan.outline, ...extra];
}
const numberOf = (id) => {
  const i = state.plan.outline.findIndex((s) => s.id === id);
  return i < 0 ? "·" : String(i + 1);
};
const titleOf = (id) => (state.plan.outline.find((s) => s.id === id) || {}).title || id;

/* The refactoring part of a feature, written in the refactoring step, is made of
   refactor sections (sections with "part": "refactoring"): they are read in their own
   tab, the code tab (id "refactor"); every other section is an explanation section, in the
   explanation tab (id "model": in a feature the Model tab, the modeling part). Both tabs are rendered into their own view, with
   the same section blocks. Sessions written before the rename mark them "part": 2. */
const isRefactorSection = (s) => s.part === "refactoring" || s.part === 2;
const inRefactoringPart = (id) => isRefactorSection(state.plan.outline.find((s) => s.id === id) || {});
/* The scoping tab (id "scoping"): a feature's scoping section ("part": "scoping"), the
   drawing of the problem the scoper builds with the user before any model, shown first,
   with its holes (the open questions anchored on it) on the elements they bear on and
   indexed at its end (see "the hole popover"), and the scoping's two buttons under the
   index (see scopingActions). While scoping runs on a drawing
   (drawingScoping), it is the only tab shown: the others appear at « End scoping », and
   hide again when a later agent's hole sends the session back to scoping. */
const isScopingSection = (s) => s.part === "scoping";
const inScoping = (id) => isScopingSection(state.plan.outline.find((s) => s.id === id) || {});
const hasScopingTab = () => state.plan.outline.some(isScopingSection);
const drawingScoping = () => hasScopingTab() && state.status.phase === "scoping";
const tabOf = (id) => (isDocAnchor(id) || rowOf(id) ? "doc" : inScoping(id) ? "scoping"
  : inRefactoringPart(id) ? "refactor" : "model");
const hasRefactorTab = () => state.plan.outline.some(isRefactorSection);
/* The narrow layout: the page in one column whenever its window is under 700px wide
   (app.css holds the same threshold), whatever the device. The metrics tab is gone from
   it, and the review pane is the review tab, after code. */
const NARROW = matchMedia("(max-width: 699.98px)");
const isNarrow = () => NARROW.matches;
/* Touch controls: the device's main pointer cannot hover (a finger on a phone or a
   tablet), chosen from the input device, never from the width (app.css reads the same
   query). What waits for a resting pointer elsewhere shows by default or answers a tap:
   « + comment » buttons always shown, dimmed (app.css); a term's tip, the new words of a
   changed passage and a side thread on a tap (see "taps"); links that would open VS
   Code on the Mac are plain code; a selection is commented from the selection bar; key
   hints name no shortcut. */
const TOUCH = matchMedia("(hover: none)");
const isTouch = () => TOUCH.matches;
// The Metrics tab (metrics.js) draws a feature's runs: other workflows have no role agents.
const hasMetricsTab = () => state.workflow === "build-feature" && !isNarrow();
const docViews = () => [$("#scoping"), $("#model"), $("#refactor"), $("#doc")];
/* The Doc tab (id "doc"): the repo docs the branch concerns, from `state.docs` (see "the
   Doc tab"). It shows once the doc set is written; a docs review (workflow review-docs)
   shows it alone, from the start. A server that sends no `docs` counts as no doc set. */
const NO_DOCS = { set: [], views: {}, stale: [], removed: [], facts: {}, triage: { text: "", list: [] }, moves: {}, reference: null };
const docsOf = () => ({ ...NO_DOCS, ...((state && state.docs) || {}) });
const isDocsReview = () => !!state && state.workflow === "review-docs";
const hasDocTab = () => isDocsReview() || docsOf().set.length > 0 || docsOf().triage.list.length > 0
  || Object.keys(docsOf().moves).length > 0;
// The tab a missing tab gives way to: the Doc tab in a docs review, the scoping tab while
// scoping runs on a drawing, the model tab otherwise.
const homeTab = () => (isDocsReview() ? "doc" : drawingScoping() ? "scoping" : "model");
// A comment, a draft or a side thread on a doc's text is anchored on the section id
// "doc:<path>"; one on the doc set list on DOC_SET, "doc:" alone. No section id starts
// with "doc:" (the server refuses it), so neither anchor names a section.
const DOC_PREFIX = "doc:";
const DOC_SET = DOC_PREFIX;
const docPathOf = (id) => {
  const s = String(id || "");
  return s.startsWith(DOC_PREFIX) && s !== DOC_SET ? s.slice(DOC_PREFIX.length) : null;
};
const isDocAnchor = (id) => String(id || "").startsWith(DOC_PREFIX);
/* A row of a Doc tab table is commented on its own anchor: "triage:<id>" for a row of the
   concept triage (store.py's TRIAGE_KEY), "moves:<id>" for a row of a README's move plan
   (MOVES_KEY). The triage's highlight baseline is kept under "triage:" alone, a move
   plan's under "moves:<path>". No section id starts with either. `rowOf` gives the kind
   and id of a row anchor, null for any other id. */
const TRIAGE_PREFIX = "triage:";
const MOVES_PREFIX = "moves:";
const ROW_KINDS = { [TRIAGE_PREFIX]: "triage", [MOVES_PREFIX]: "passage" };
const rowOf = (id) => {
  const s = String(id || "");
  const prefix = Object.keys(ROW_KINDS).find((p) => s.startsWith(p) && s.length > p.length);
  return prefix ? { kind: ROW_KINDS[prefix], id: s.slice(prefix.length) } : null;
};
// Rewritten since its highlight baseline: the text at the last batch sent, or at « mark
// read » (the server compares with seen.json).
const isUpdated = (id) => !!(state.sections[id] || {}).updated;

function render() {
  const { plan } = state;
  // A mark in the tab title while an agent question waits, and the progress of a writing
  // run, to be seen from another window.
  const run = writingRun();
  document.title = `${openQuestions().length ? "● " : ""}${run ? `${run.k}/${run.set.length} · ` : ""}${plan.title} · view-concept`;
  $("#title").textContent = plan.title;
  renderListening();
  renderPublish();
  renderPr();
  renderReference();
  renderStatus();
  followSession();
  renderPlan();
  renderSections();
  renderReview();
  renderPopover(); // a sent batch changes what the open thread offers
}

/* ---------------- tabs ----------------
   The plan, the explanation, the code tab and the Doc tab share one space; one is shown
   at a time. The code tab exists only once a section is in the refactoring part, the Doc
   tab once the doc set is written (in a docs review it is the only tab, and the others
   are hidden). The tab follows the
   session at the moments that matter — scoping starting (its questions are in the scope
   block, on the Plan tab), the plan waiting for approval, the writing starting (in the
   tab of the section being written) — and otherwise stays where the user put it. A
   model waiting for approval does not move it, nor does a PR waiting to be created:
   « Approve model » sits at the end of the explanation, where the model is read, and
   « Create PR » at the end of the code tab. A feature also has the Metrics tab,
   which fetches its numbers when shown and again on each state update while shown.
   While scoping runs on a drawing, the scoping tab is the only one, and the tab follows
   it there in place of the Plan tab.
   Tab ids and keys: 0 "scoping", 1 "plan", 2 "model" (the explanation, named « model » in a branch
   review), 3 "refactor" (code), 4 "doc", 5 "metrics". In the narrow layout the Doc tab
   comes after code, before review. */

function setTab(name) {
  // A tab id this page has no view for (a position saved by an older page): the model tab.
  if (name !== "review" && !$(`.view[data-view="${CSS.escape(String(name))}"]`)) name = "model";
  if (name === "scoping" && !hasScopingTab()) name = homeTab();
  if (drawingScoping() && name !== "review") name = "scoping"; // the scoping tab alone
  if (name === "refactor" && !hasRefactorTab()) name = homeTab();
  if (name === "doc" && !hasDocTab()) name = homeTab();
  if (name === "metrics" && !hasMetricsTab()) name = homeTab();
  if (name === "review" && !isNarrow()) name = homeTab();
  if (isDocsReview() && name !== "review") name = "doc"; // the Doc tab alone
  releaseAnchor(); // the page is about to move the view, or show another one
  tab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  document.body.classList.toggle("on-review", name === "review");
  if (name === "review") { const pane = $(".review"); if (reviewAtEnd) pane.scrollTop = pane.scrollHeight; }
  $("#sel-actions").hidden = true;
  if (name !== "review") renderMermaid($(`.view[data-view="${name}"]`));
  positionPopover();
  if (name === "metrics") refreshMetrics();
  savePosition();
}

/* The tab follow rule moves the tab only on a phase change it sees while the page is on
   the session. At load, the saved position's tab opens (the model tab when that tab is
   no longer shown), whatever the phase; without one, the tab is picked from the phase. */
function followSession() {
  const phase = shownPhase();
  const onPlan = ["scoping", "awaiting-approval"].includes(phase);
  if (tab === null) {
    if (!restorePosition()) setTab(isDocsReview() ? "doc" : drawingScoping() ? "scoping"
      : Object.keys(state.sections).length && !onPlan ? "model" : "plan");
    positionReady = true;
  } else if (phase !== lastPhase && !isDocsReview()) {
    if (onPlan) setTab(drawingScoping() ? "scoping" : "plan");
    // A run opens on the tab of the set's first section not written yet.
    if (phase === "writing") setTab(tabOf(writingId() || (writingRun() || { set: [""] }).set[0]));
  }
  lastPhase = phase;
  $('.tab[data-tab="scoping"]').hidden = !hasScopingTab();
  if (tab === "scoping" && !hasScopingTab()) setTab(homeTab());
  $('.tab[data-tab="refactor"]').hidden = !hasRefactorTab();
  if (tab === "refactor" && !hasRefactorTab()) setTab(homeTab());
  $('.tab[data-tab="doc"]').hidden = !hasDocTab();
  if (tab === "doc" && !hasDocTab()) setTab(homeTab());
  $('.tab[data-tab="metrics"]').hidden = !hasMetricsTab();
  if (tab === "metrics" && !hasMetricsTab()) setTab(homeTab());
  for (const name of ["plan", "model"]) $(`.tab[data-tab="${name}"]`).hidden = isDocsReview();
  if (isDocsReview() && tab !== "doc" && tab !== "review") setTab("doc");
  // While scoping runs on a drawing, the scoping tab is the only one.
  if (drawingScoping()) {
    for (const name of ["plan", "model", "refactor", "doc", "metrics"]) $(`.tab[data-tab="${name}"]`).hidden = true;
    if (tab !== "scoping" && tab !== "review") setTab("scoping");
  }
  // In a feature, the explanation is the modeling part, so its tab is named after the model.
  const modelLabel = state.workflow === "build-feature" ? "model" : "explanation";
  $('.tab[data-tab="model"]').title = `${modelLabel[0].toUpperCase()}${modelLabel.slice(1)} (2)`;
  for (const [name, label] of [["scoping", "scoping"], ["model", modelLabel], ["refactor", "code"]]) {
    const n = Object.keys(state.sections).filter((id) => isUpdated(id) && tabOf(id) === name).length;
    const writing = !!writingId() && tabOf(writingId()) === name;
    $(`.tab[data-tab="${name}"]`).replaceChildren(...[label,
      n ? el("span", { class: "badge new", text: `${n} updated` }) : null,
      writing ? el("span", { class: "badge accent writing", text: "writing" }) : null].filter(Boolean));
  }
  // The Doc tab's badge counts the docs rewritten, or whose missing facts changed, since
  // their highlight baseline.
  const docs = docsOf();
  const n = docs.set.filter((d) => (docs.views[d.path] || {}).updated || factsUpdated(d.path)).length
    + (docs.triage.list.some((r) => r.updated) ? 1 : 0)
    + Object.values(docs.moves).filter((m) => m.list.some((r) => r.updated)).length;
  $('.tab[data-tab="doc"]').replaceChildren(...["doc", n ? el("span", { class: "badge new", text: `${n} updated` }) : null].filter(Boolean));
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

/* Crossing the threshold: the tab a layout lacks gives way to the explanation. */
NARROW.addEventListener("change", () => {
  if (!state) return;
  closeMenu();
  $('.tab[data-tab="metrics"]').hidden = !hasMetricsTab();
  if ((tab === "review" && !isNarrow()) || (tab === "metrics" && isNarrow())) setTab(homeTab());
  setReviewWidth(isNarrow() ? null : loadJSON(WIDTH_KEY, null));
});

/* The ⋯ menu of the narrow layout: the header's buttons, open on a tap of ⋯, closed by
   a tap on one of them or anywhere else. */
const menu = $("#header-menu"), menuToggle = $("#menu-toggle");
function closeMenu() { menu.classList.remove("open"); menuToggle.setAttribute("aria-expanded", "false"); }
menuToggle.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = !menu.classList.contains("open");
  menu.classList.toggle("open", open);
  menuToggle.setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (e) => {
  if (!menu.classList.contains("open")) return;
  if (!e.target.closest("#header-menu") || e.target.closest("button, a")) closeMenu();
});
document.addEventListener("keydown", (e) => {
  if (!state || e.target.closest("textarea, input") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "0" && hasScopingTab()) setTab("scoping");
  if (e.key === "1") setTab("plan");
  if (e.key === "2") setTab("model");
  if (e.key === "3" && hasRefactorTab()) setTab("refactor");
  if (e.key === "4" && hasDocTab()) setTab("doc");
  if (e.key === "5" && hasMetricsTab()) setTab("metrics");
});

/* ---------------- status + approvals ---------------- */

/* The agent is listening while a watch runs for the session (the server reads the watch's
   heartbeat). It says whether a batch is read now; the « live » dot only says whether
   the page is connected to the server. */
function renderListening() {
  const l = $("#listening");
  l.className = `listening ${state.listening ? "on" : "off"}`;
  // The narrow layout shows the dot alone (the listening dot).
  l.replaceChildren(el("span", { class: "l-dot", text: state.listening ? "●" : "○" }),
    el("span", { class: "l-text", text: state.listening ? " Agent listening" : " Agent not listening" }));
}
// What a successful send says when no watch reads it: the batch waits in the inbox.
const NOT_LISTENING = "The agent isn't listening: write anything in the terminal and it will read this batch";
const sentToast = (msg) => toast(state.listening ? msg : NOT_LISTENING, state.listening ? 3000 : 8000);

/* The phase the banner shows: the one the agent declared, or the derived phase when a
   trace in the session files (a new section file, the plan, the audit) came after the
   agent's last status call (the server computes it). The banner wording, the writing
   badge and the tab follow read it; the buttons stay on the declared phase, since only
   the agent's call opens or closes what they answer. An older server sends no `shown`. */
const shownPhase = () => state.status.shown || state.status.phase;

/* A writing run, as the server reads it from the section files: its run set (the
   sections it writes, in outline order) and those written in this run (file modified
   after the run began). The section named is the first of the set not written yet, ""
   once the whole set is written (the run is finishing). Null when the banner shows no
   writing run, or when an older server sends no run. */
function writingRun() {
  const run = state.status.run;
  if (shownPhase() !== "writing" || !run || !(run.set || []).length) return null;
  const written = new Set(run.written || []);
  return { set: run.set, k: run.set.filter((id) => written.has(id)).length,
           named: run.set.find((id) => !written.has(id)) || "" };
}

/* The one section badged « writing »: the section the banner names. A run declares
   several sections, but nothing on disk says which one is being written until its file
   lands, so the page marks only the first one missing, and none while the run is finishing.
   Without a run (older server) it falls back to the section the agent declared. */
function writingId() {
  if (shownPhase() !== "writing") return "";
  const run = writingRun();
  return run ? run.named : state.status.section || "";
}

// The banner of a writing run: the section named and the progress, or « finishing ».
function writingLabel() {
  const run = writingRun();
  if (!run) return state.status.section ? `writing §${numberOf(state.status.section)} ${titleOf(state.status.section)}` : "writing";
  const n = run.set.length;
  return run.named ? `writing §${numberOf(run.named)} ${titleOf(run.named)} · ${run.k}/${n} written` : `${n}/${n} written · finishing`;
}

/* "awaiting-answer" waits on the open agent questions, answered from their boxes in the
   scope block (see "agent questions" below), so it has no button here. */
const QUESTION_LABELS = { ready: "question · waiting for your answer", sent: "answered · the agent is reading it" };

/* Five phases wait for the user: the plan of an explanation ("awaiting-approval"), the
   model of a feature at the end of model consolidation ("awaiting-model", set by the
   build-feature skill only), the doc pass once the code carries the model ("awaiting-docs",
   build-feature too), the doc pass stopped on the move plans of restructured READMEs
   ("awaiting-moves", build-feature too: the README's skeleton is written, document-feature's
   folder models wait; « Write READMEs » under the plans in the Doc tab, action
   "write-readmes"), and the opening of its PR ("awaiting-pr", build-feature and review-docs).
   Each is answered from the page by a batch carrying the phase's action, draft comments
   included. Until the agent moves the status on, the page says the answer is on its way.
   « Approve plan » sits at the top of the Plan tab, and the page switches to it.
   « Approve model » sits at the end of the explanation, after the last section of the modeling part,
   where the model is read; « Write docs » (action "write-docs") and « Write docs and create
   PR » (the same action with `then_pr: true` in the batch: the doc pass, the reviewer's run
   and the PR with no pause) at the end of the code tab; « Create PR » at the end of the
   code tab, at the end of the Doc tab in a docs review. The page does not switch tabs for
   them. */
const modelButton = el("button", { id: "model-approve", class: "btn primary approve doc-approve", hidden: true });
const prButton = el("button", { id: "pr-create", class: "btn primary approve doc-approve", hidden: true });
const movesButton = el("button", { id: "readmes-write", class: "btn primary approve doc-approve", hidden: true,
                                   title: "The doc pass resumes: the document-feature agent writes the folder models of every README of the doc set, the restructured ones from the move plans and your comments on them" });
const docsButton = el("button", { id: "docs-write", class: "btn primary approve doc-approve", hidden: true,
                                  title: "The doc pass: the documenter refreshes the doc set, write-readme agents write the README's skeleton of each README, then a document-feature agent writes the folder models" });
const docsPrButton = el("button", { id: "docs-write-pr", class: "btn approve doc-approve", hidden: true,
                                    title: "The doc pass, the reviewer's run on the doc items and stale passages, then the PR, with no pause" });
// Once the agent opened the PR (plan.json's `pr`), the page links it in the top bar and at
// the end of the code tab, under « Create PR » (« Update PR » from then on).
const prEnd = el("a", { id: "pr-end", class: "btn doc-approve", target: "_blank", rel: "noopener", hidden: true });
const prLabel = (url) => { const m = /\/pull\/(\d+)/.exec(url); return m ? `PR #${m[1]}` : "PR"; };

function renderPr() {
  const pr = state.plan.pr;
  for (const a of [$("#pr-link"), prEnd]) {
    a.hidden = !pr;
    if (!pr) continue;
    a.href = pr.url;
    a.title = pr.url;
    a.textContent = a === prEnd ? `Open ${prLabel(pr.url)} ↗` : `${prLabel(pr.url)} ↗`;
  }
}
/* A docs review that takes a feature's model as reference model links that session
   in the top bar, with the reason the agent kept it next to the link; it opens in another
   browser tab. No reference, the ordinary case, shows neither. */
function renderReference() {
  const ref = docsOf().reference;
  const a = $("#reference-link");
  const why = $("#reference-reason");
  a.hidden = !ref;
  why.hidden = !(ref && ref.reason);
  if (!ref) return;
  a.href = ref.url || `/s/${encodeURIComponent(ref.slug)}`;
  a.textContent = `reference: ${ref.title || ref.slug} ↗`;
  a.title = `The reference model: session ${ref.slug}`;
  why.textContent = why.title = ref.reason || "";
}

const APPROVALS = {
  "awaiting-approval": { action: "approve-plan", label: "Approve plan", toast: "Plan approved",
                         ready: "plan ready · waiting for your approval", sent: "plan approved · the agent is starting" },
  "awaiting-model": { action: "approve-model", label: "Approve model", toast: "Model approved", button: modelButton,
                      ready: "model ready · waiting for your approval", sent: "model approved · the agent is implementing" },
  "awaiting-docs": { action: "write-docs", label: "Write docs", toast: "Docs requested", button: docsButton,
                     ready: "code carries the model · waiting for you to write the docs",
                     sent: "docs requested · the doc pass is writing them",
                     // The second button: the same action, the PR chained after the doc pass.
                     also: { button: docsPrButton, label: "Write docs and create PR", toast: "Docs and PR requested",
                             extra: { then_pr: true }, sent: "docs and PR requested · the doc pass is writing the docs" } },
  "awaiting-moves": { action: "write-readmes", label: "Write READMEs", toast: "READMEs requested", button: movesButton,
                      ready: "move plan ready · waiting for you to read it",
                      sent: "READMEs requested · the doc pass is writing them" },
  "awaiting-pr": { action: "create-pr", label: "Create PR", toast: "PR requested", button: prButton,
                   ready: "refactoring written · waiting for you to create the PR",
                   sent: "PR requested · the agent is opening it" },
};
const buttonOf = (approval) => approval.button || $("#approve");

const lastBatchOf = (action) => state.comments.batches.filter((b) => b.action === action).pop() || {};

function approvalPending() {
  const approval = APPROVALS[state.status.phase];
  if (!approval) return false;
  const since = state.status.since || "";
  return state.comments.batches.some((b) => b.action === approval.action && b.sent >= since);
}

/* Batch progress: where your last batch stands, in every phase. The server sends its
   stage: "sent" (it waits in the inbox), "received" (the delivery mark passed it: the
   agent has it), "acted" (the agent wrote a session file after receiving it). Until it
   is acted on, the banner names what you sent and where it stands, in place of the
   phase's wording; then the phase takes over, and the wordings the page used to fix at
   the click (« model approved · the agent is implementing »…) are true. */
const BATCH_WHAT = { answer: "answered", "go-on": "going on", "approve-plan": "plan approved",
                     "approve-model": "model approved", "write-docs": "docs requested", "create-pr": "PR requested", plan: "scoping ended",
                     grill: "grill", "stop-grill": "grill stopped",
                     "rewrite-readme": "README rewrite requested", "write-lexicon": "repo lexicon requested",
                     "write-readmes": "READMEs requested", missing: "asked what's missing", "end-scoping": "scoping ended" };
const BATCH_STAGE = { sent: "in the inbox", received: "the agent has it" };

function batchProgress() {
  const b = state.batch;
  if (!b || !BATCH_STAGE[b.stage]) return "";
  // A « Write docs and create PR » batch carries then_pr (the batch in comments.json).
  const chained = b.action === "write-docs" && state.comments.batches.some((x) => x.id === b.id && x.then_pr);
  const what = chained ? "docs and PR requested" : b.action ? BATCH_WHAT[b.action] || b.action : "comments";
  return `${what} · ${BATCH_STAGE[b.stage]}`;
}

/* The inactivity notice: a phase at work keeps its moving label until another phase is
   declared, so an agent that stopped mid-run would look busy for good. Once the agent has
   written no session file for ten minutes (`state.activity`, the time of the last one;
   the page's own writes and the watch's heartbeat do not count), the banner adds the
   count of quiet minutes. It claims nothing more: a long read looks the same as a run
   that ended without a status call. Never on a banner that waits for you. */
const QUIET_MIN = 10;

function quietNotice() {
  const last = Date.parse(state.activity || "");
  if (Number.isNaN(last)) return "";
  const min = Math.floor((Date.now() - last) / 60000);
  return min >= QUIET_MIN ? `no activity for ${min} min` : "";
}
// The count goes up with no file changing, so no event from the server: redraw on a timer.
setInterval(() => { if (state) renderStatus(); }, 30000);

// The phases at work: the banner shows them in the active colour, with its moving dots.
const AT_WORK = ["planning", "writing", "audit", "revising"];

/* What the banner says, and whether it shows the agent at work (`active`) or waits for
   the user (`ask`). Batch progress comes first, in every phase. A derived phase (writing, planning or the audit, read from a trace
   later than the agent's last status call) takes the wording of that phase; the declared
   phase's message is dropped with it, since it described the step the trace ended. */
function banner() {
  const { phase, message } = state.status;
  const progress = batchProgress();
  if (progress) return { text: progress, active: true, ask: false };
  const shown = shownPhase();
  if (shown !== phase) {
    const text = shown === "writing" ? writingLabel() : { planning: "drafting the plan", audit: "vocabulary audit" }[shown] || shown;
    return { text, active: true, ask: false };
  }
  const approval = APPROVALS[phase];
  const asking = ["scoping", "awaiting-answer"].includes(phase) && openQuestions().length > 0 && !goOnPending();
  // The PR recorded after the last « Create PR »: the agent opened (or updated) it.
  const prReady = phase === "awaiting-pr" && approvalPending() && !!state.plan.pr &&
                  state.plan.pr.at >= lastBatchOf("create-pr").sent;
  // The agent declared it has nothing more to ask, and nothing moved since (the server
  // clears the mark on a new question or a batch): the banner waits for « Write plan ».
  const scopingDone = phase === "scoping" && !asking && !planPending() && !!state.status.scoping_done;
  const labels = {
    // Scoping runs while the agent asks; its questions wait in the scope block, and « Write plan » ends it.
    // On a drawing, the questions are holes on its elements, and « End scoping » ends it.
    scoping: drawingScoping() ? (sentSince("end-scoping") ? "scoping ended · the planner is converting the drawing"
           : asking ? "scoping · holes waiting for you"
           : state.status.scoping_done ? "scoping done · End scoping when ready"
           : repliedInScoping() ? "reading your reply"
           : "drawing the problem")
           : asking ? "scoping · questions waiting for you"
           : planPending() ? `scoping ended · the agent is ${rewriting() ? "revising" : "writing"} the ${scopingProduct()}`
           : scopingDone ? "scoping done · Write plan when ready"
           : repliedInScoping() ? "reading your reply"
           : "scoping the question",
    planning: "drafting the plan",
    ...(approval ? { [phase]: approvalPending() ? approvalSent(approval) : approvalReady(approval) } : {}),
    ...(prReady ? { [phase]: `${prLabel(state.plan.pr.url)} ready · open it from the top bar` } : {}),
    "awaiting-answer": goOnPending() ? "going on · the writer is writing the next sections"
                     : openQuestions().length ? QUESTION_LABELS.ready : QUESTION_LABELS.sent,
    // While the run is finishing, the phase is still at work: same colour, no section named.
    writing: writingLabel(),
    audit: "vocabulary audit",
    revising: "revising",
  };
  const active = (phase === "scoping" && !asking && !scopingDone) || AT_WORK.includes(phase) ||
                 (approval && approvalPending() && !prReady) || (phase === "awaiting-answer" && !asking);
  const text = labels[phase] ? [labels[phase], message].filter(Boolean).join(" · ") : "";
  return { text, active, ask: !!((approval && !approvalPending()) || asking || scopingDone) };
}

/* In scoping, a batch you sent after the agent's last question (or its last status call,
   if later): the agent is reading your answers or comments, until it asks again or
   declares scoping done. With nothing sent since, the banner keeps « scoping the
   question ». Same-second times count as after, as in approvalPending. */
// The banner while a phase's batch is on its way: « Write docs and create PR » has its own.
const approvalSent = (approval) =>
  (approval.also && lastBatchOf(approval.action).then_pr ? approval.also.sent : approval.sent);
// A docs review waits for « Create PR » once its docs are written, with no refactoring.
const approvalReady = (approval) =>
  (approval.action === "create-pr" && isDocsReview() ? "docs written · waiting for you to create the PR" : approval.ready);

function repliedInScoping() {
  const asked = (state.questions || []).flatMap((q) => [q.asked, q.reasked]).filter(Boolean);
  const since = [...asked, state.status.since || ""].reduce((a, b) => (b > a ? b : a), "");
  return state.comments.batches.some((b) => b.sent >= since);
}

function renderStatus() {
  const { phase } = state.status;
  const approval = APPROVALS[phase];
  const b = banner();
  const p = $("#phase");
  p.hidden = !b.text;
  p.className = `phase ${b.active ? "active" : ""} ${b.ask ? "ask" : ""}`;
  p.textContent = [b.text, b.active && !b.ask ? quietNotice() : ""].filter(Boolean).join(" · ");

  $("#approve").hidden = modelButton.hidden = prButton.hidden = docsButton.hidden = docsPrButton.hidden = movesButton.hidden = true;
  if (!approval) return;
  const n = drafts.filter(ready).length;
  const withDrafts = (label) => (n ? `${label} + send ${n} comment${n > 1 ? "s" : ""}` : label);
  const btn = buttonOf(approval);
  btn.hidden = approvalPending();
  btn.textContent = withDrafts(phase === "awaiting-pr" && state.plan.pr ? "Update PR" : approval.label);
  if (approval.also) {
    approval.also.button.hidden = approvalPending();
    approval.also.button.textContent = withDrafts(approval.also.label);
  }
}

for (const b of [$("#approve"), modelButton, prButton, docsButton, movesButton]) b.addEventListener("click", () => {
  const approval = APPROVALS[state.status.phase];
  if (approval) send(approval.action);
});
docsPrButton.addEventListener("click", () => {
  const approval = APPROVALS[state.status.phase];
  if (approval && approval.also) send(approval.action, approval.also.button, approval.also.extra);
});

function renderPlan() {
  const { plan } = state;
  renderScope();
  // A feature logs every change of the model: its last entry says what moved last.
  // Other sessions state their last plan revision in plan.json.
  const changes = state.changes || [];
  const last = changes.length && changes[changes.length - 1].cause ? changes[changes.length - 1].change : "";
  const rev = $("#revision");
  if (last || plan.revision) {
    rev.hidden = false;
    rev.replaceChildren(
      el("span", { class: planChanged ? "badge flag" : "badge", text: planChanged ? "revised" : last ? "last change" : "last revision" }),
      " ", last || plan.revision,
    );
    rev.onclick = () => { planChanged = false; renderPlan(); };
  } else rev.hidden = true;

  $("#outline").replaceChildren(...allSections().map((s) => {
    const written = s.id in state.sections;
    return el("li", { class: `${written ? "" : "pending"} ${isUpdated(s.id) ? "updated" : ""}`,
                      onclick: () => scrollToSection(s.id) },
      el("button", { class: "o-comment", text: "+ comment", title: "Comment on this item of the plan",
                     onclick: (e) => {
                       e.stopPropagation();
                       openComposer({ section: s.id, quote: `plan · ${s.title}`, prefix: "", rect: e.target.getBoundingClientRect() });
                     } }),
      el("div", { class: "o-title" },
        el("span", { class: "num", text: numberOf(s.id) }), " ", s.title,
        writingId() === s.id ? el("span", { class: "badge accent writing", text: "writing" }) : null,
        isUpdated(s.id) ? el("span", { class: "badge new", text: "updated" }) : null),
      s.earns ? el("div", { class: "o-earns muted", text: s.earns }) : null);
  }));

  renderChanges();

  const lex = $("#lexicon");
  lex.replaceChildren();
  if (!plan.lexicon.length) {
    lex.append(el("tr", {}, el("td", { class: "dim", text: "no terms yet" })));
    return;
  }
  for (const t of plan.lexicon) {
    lex.append(el("tr", { onclick: () => scrollToSection(t.section) },
      el("td", { class: "term", text: t.term }),
      el("td", { class: "sec dim", text: `§${numberOf(t.section)}` }),
      el("td", { class: "def", text: t.definition || "" })));
  }
}

/* In a feature, once the model is approved, the changes logged after the last one an
   implementer took into account are not implemented yet: the code does not carry them. */
const unimplemented = () => new Set(state.unimplemented || []);
const lagLine = () => {
  const ids = state.unimplemented || [];
  if (!ids.length) return null;
  return el("p", { class: "lag", text: `${ids.length} model change${ids.length === 1 ? "" : "s"} not implemented yet: ${ids.join(", ")}` });
};

function renderChanges() {
  const list = state.changes || [];
  const pending = unimplemented();
  $("#changes-head").hidden = !list.length;
  $("#changes").replaceChildren(...list.map((d) => {
    // An entry of the change history says who made it and what caused it; one written
    // before the change history (changes.json) has why, instead and files.
    const meta = [d.by, d.cause && d.cause.length ? `cause: ${d.cause.join(", ")}` : ""].filter(Boolean).join(" · ");
    const item = el("li", { class: pending.has(d.id) ? "change unimplemented" : "change" },
      el("div", {}, el("span", { class: "num", text: d.id }), " ", d.change,
        pending.has(d.id) ? el("span", { class: "lag-tag", text: " · not implemented yet" }) : null),
      meta ? el("div", { class: "d-why muted", text: meta }) : null,
      d.instead ? el("div", { class: "d-instead dim", text: `rather than ${d.instead}` }) : null,
      d.why ? el("div", { class: "d-why muted", text: d.why }) : null);
    if (d.files && d.files.length) {
      const files = el("div", { class: "d-files" });
      d.files.forEach((f) => {
        const href = vscodeHref(f);
        files.append(href ? el("a", { class: "cite", href, text: f }) : el("code", { text: f }), " ");
      });
      item.append(files);
    }
    return item;
  }));
}

/* ---------------- reading position ----------------
   A render rebuilds the whole tab, and what it holds above the reader keeps changing
   height for a while after it: a Mermaid chart is a code block until it is drawn, a new
   section frame is 150px high until it posts its height. The browser's own scroll
   anchoring cannot hold the view, since the element it held is gone. So before a render
   the page notes the reading anchor: the element with an id at the top of the view (the
   section, or the item's description) and, in a section, the block of its body there,
   with its distance from the view's top. After the render, and at every later change of
   height in the tab, the view scrolls so that the anchor is back at that distance. The
   anchor is held until the reader scrolls or the page scrolls to a passage. While a
   smooth scroll the page started is running (to a passage or a section), a
   render notes no anchor: holding one would set scrollTop and stop that scroll short. */

let anchor = null; // { view, key, block, offset, text, words, ranks, node }
let pageScrolling = null; // { view } of the smooth scroll the page is running

/* Runs a smooth scroll of the page in `view`, and marks it as running until the view's
   scrollend; a scroll that moves nothing fires no scrollend, so the mark also goes when
   no scroll event came in the next 200 ms. */
function pageScroll(view, scroll) {
  if (!view) { scroll(); return; }
  const run = { view };
  pageScrolling = run;
  let moved = false;
  const onScroll = () => { moved = true; };
  const done = () => {
    view.removeEventListener("scroll", onScroll);
    view.removeEventListener("scrollend", done);
    if (pageScrolling === run) pageScrolling = null;
  };
  view.addEventListener("scroll", onScroll, { passive: true });
  view.addEventListener("scrollend", done, { once: true });
  setTimeout(() => { if (!moved) done(); }, 200);
  scroll();
}

/* The block key: how the reading anchor names its block, by the first 80 characters of
   the block's text (its words joined by spaces), with the block's rank and the words of
   the whole element's body at the time it is noted. After a render, the block is found
   in that element only, by these questions in order:
   - the element is gone: no block (the view does not move);
   - a block starts with the key: that block, the closest to the old rank among several;
   - else the old and new words are paired (diffWords) and, with fewer than half of the
     old words paired, the first block (the section was rewritten);
   - else the block holding the pair of the first paired word of the old block;
   - else the block of the word that follows, in the new version, the last word paired
     before the old block (the text written in its place);
   - else the first block.
   In an HTML section the block is the whole section frame: the page cannot see the
   blocks drawn in it, only the distance from the frame's top is kept. */
const KEY_LENGTH = 80;

// The body of an anchored element: a section's, or the section block of an item's description.
const bodyOf = (node) => node.querySelector(":scope > .body, :scope > td > .sec > .body");
/* A block's words and text, cut the way the change highlights cut them (words): a formula
   counts as its TeX and a diagram as its source, so a re-typeset formula or a drawn SVG
   keeps the block's key and words. A block that is itself a formula or a diagram (a
   display formula, a drawn diagram, or the `pre` of its source before the drawing) is
   that one word: words() reads only below the element it is given. */
function blockWords(b) {
  const atom = atomOf(b) ?? (b.matches("pre") ? b.querySelector(":scope > code.language-mermaid") : null)?.textContent;
  return atom != null ? [`\u0000${collapse(atom)}`] : words(b).map((w) => w.text);
}
const blockText = (b) => blockWords(b).join(" ");

// The words of a body's blocks, each with the rank of its block.
function bodyWords(body) {
  const list = [], ranks = [];
  [...body.children].forEach((b, k) => {
    for (const w of blockWords(b)) { list.push(w); ranks.push(k); }
  });
  return { words: list, ranks };
}

function noteBlock(a, body, block) {
  a.block = block;
  a.text = block >= 0 && body ? blockText(body.children[block]).slice(0, KEY_LENGTH) : "";
  Object.assign(a, body ? bodyWords(body) : { words: [], ranks: [] });
  return a;
}

function readingAnchor(view) {
  const top = view.getBoundingClientRect().top;
  // In document order, the first element still reaching the view's top is the outermost.
  const node = [...view.querySelectorAll("[id]")].find((n) => {
    const r = n.getBoundingClientRect();
    return r.height && r.bottom > top;
  });
  if (!node) return null;
  const body = bodyOf(node);
  const blocks = [...(body || { children: [] }).children];
  const block = blocks.findIndex((b) => b.getBoundingClientRect().bottom > top);
  const at = block < 0 ? node : blocks[block];
  return noteBlock({ view, key: node.id, offset: at.getBoundingClientRect().top - top, node: at }, body, block);
}

// The block of `blocks` the anchor `a` names, by the questions above.
function findBlock(a, blocks) {
  if (a.text) {
    const keyed = blocks.map((b, k) => k).filter((k) => blockText(blocks[k]).startsWith(a.text));
    if (keyed.length) return keyed.reduce((x, k) => (Math.abs(k - a.block) < Math.abs(x - a.block) ? k : x));
  }
  if (!a.words || !a.words.length) return Math.min(a.block, blocks.length - 1);
  const now = bodyWords({ children: blocks });
  const { pairs } = diffWords(a.words, now.words);
  const paired = pairs.filter((j) => j >= 0).length;
  if (paired * 2 < a.words.length) return 0;
  let first = -1, before = -1;
  a.words.forEach((w, i) => {
    if (pairs[i] < 0) return;
    if (a.ranks[i] < a.block) before = i;
    else if (a.ranks[i] === a.block && first < 0) first = i;
  });
  if (first >= 0) return now.ranks[pairs[first]];
  if (before >= 0) return now.ranks[Math.min(pairs[before] + 1, now.words.length - 1)];
  return 0;
}

/* The DOM node the anchor `a` names: its block, or the element itself when the anchor has
   no block; null when the element is gone. Found once per render, then re-noted from what
   was found, so the next render compares with the text the reader had last. */
function anchorNode(a) {
  if (a.node && a.node.isConnected) return a.node;
  const node = a.view.querySelector(`[id="${CSS.escape(a.key)}"]`);
  if (!node) return (a.node = null);
  const body = bodyOf(node);
  const blocks = [...(body || { children: [] }).children];
  if (a.block < 0 || !blocks.length) return (a.node = node);
  const block = findBlock(a, blocks);
  noteBlock(a, body, block);
  return (a.node = blocks[block]);
}

function holdAnchor() {
  const node = anchor && anchorNode(anchor);
  if (!node || !node.getClientRects().length) return;
  const drift = node.getBoundingClientRect().top - anchor.view.getBoundingClientRect().top - anchor.offset;
  if (Math.abs(drift) >= 1) anchor.view.scrollTop += drift;
}

const releaseAnchor = () => { anchor = null; };
const anchorWatch = new ResizeObserver(holdAnchor);
for (const view of docViews()) {
  for (const type of ["wheel", "touchstart", "keydown", "mousedown"]) {
    view.addEventListener(type, releaseAnchor, { passive: true });
  }
}

/* ---------------- saved position ----------------
   What the page keeps of the reader's place in this session, in this browser's storage
   (one per session, like the drafts): the open tab, the reading anchor of the view shown
   (with its block key; the Plan and Metrics tabs keep only the tab), the open item
   entries of the code tab, and the doc shown in the Doc tab. Written at the end of a scroll, at a change of tab, when an
   item entry opens or closes, and when the page goes away; put back at every load of the
   session (a click in the sessions list, `view-concept open`, a reload). */

let positionReady = false; // false until the saved position is put back: nothing is written before
let positionTimer = null;

function savePosition() {
  if (!positionReady) return;
  const view = docViews().find((v) => v.dataset.view === tab);
  const a = !view ? null : anchor && anchor.view === view ? anchor : view.scrollTop ? readingAnchor(view) : null;
  saveJSON(POSITION_KEY, {
    tab,
    anchor: a && { view: view.dataset.view, key: a.key, block: a.block, offset: a.offset, text: a.text, words: a.words, ranks: a.ranks },
    open: [...openItems],
    doc: shownDoc,
  });
}

/* Puts back the saved position, if any: its open item entries, its tab, and its reading
   anchor, held until the first render has placed it. Returns whether there was one. */
function restorePosition() {
  const saved = loadJSON(POSITION_KEY, null);
  if (!saved || !saved.tab) return false;
  for (const id of saved.open || []) openItems.add(id);
  if (saved.doc) shownDoc = saved.doc;
  setTab(saved.tab);
  const view = docViews().find((v) => v.dataset.view === tab);
  if (view && saved.anchor && saved.anchor.view === tab) anchor = { ...saved.anchor, view, restore: true };
  return true;
}

for (const view of docViews()) {
  view.addEventListener("scroll", () => {
    clearTimeout(positionTimer);
    positionTimer = setTimeout(savePosition, 250);
  }, { passive: true });
}
addEventListener("pagehide", savePosition);

function renderSections() {
  const model = $("#model");
  const sections = allSections();
  const shown = docViews().find((v) => v.classList.contains("active"));
  if (pageScrolling) anchor = null;
  else if (anchor && anchor.restore) { /* the saved position, placed after this render */ }
  else if (!anchor || anchor.view !== shown || !anchorNode(anchor)) anchor = shown && shown.scrollTop ? readingAnchor(shown) : null;
  parkFrames();
  // A question box at the end of a section is re-attached on each render: keep its focus.
  const active = document.activeElement;
  // (the scope block too: a docs review shows it at the top of the Doc tab, re-attached)
  const keep = active && active.closest && active.closest(".sec-questions, #scope, .doc-editor")
    ? [active, active.selectionStart, active.selectionEnd, active.scrollTop] : null;
  // « Create PR » ends the code tab, or the Doc tab in a docs review.
  const prEnding = [prButton, prEnd];
  if (!sections.length) {
    model.replaceChildren(el("p", { class: "dim empty", text: "Waiting for the plan…" }));
    $("#scoping").replaceChildren();
    $("#refactor").replaceChildren();
  } else {
    $("#scoping").replaceChildren(...sections.filter((s) => tabOf(s.id) === "scoping").map((s) => sectionBlock(s)),
      ...[scopingActions()].filter(Boolean));
    model.replaceChildren(...sections.filter((s) => tabOf(s.id) === "model").map((s) => sectionBlock(s)), modelButton);
    $("#refactor").replaceChildren(...[lagLine()].filter(Boolean),
      ...refactorTab(sections.filter((s) => tabOf(s.id) === "refactor")), docsButton, docsPrButton,
      ...(isDocsReview() ? [] : prEnding));
  }
  renderDocTab(isDocsReview() ? prEnding : []);
  for (const view of docViews()) {
    typesetMath(view);
    linkCitations(view);
    renderMermaid(view);
    if (view.id === "doc") annotateDocTerms(view);
    else { annotateAudit(view); annotateLexicon(view); }
    annotateQuestions(view);
  }
  if (keep && keep[0].isConnected && document.activeElement !== keep[0]) {
    keep[0].focus({ preventScroll: true });
    if (keep[1] != null) keep[0].setSelectionRange(keep[1], keep[2]);
    keep[0].scrollTop = keep[3];
  }
  placeFrames();
  holdAnchor();
  if (anchor && anchor.restore) {
    delete anchor.restore;
    if (!anchorNode(anchor)) anchor = null; // the element is gone: the tab opens at its top
  }
  anchorWatch.disconnect();
  for (const view of docViews()) for (const child of view.children) anchorWatch.observe(child);
  frames.forEach((f, id) => { postTerms(id, f); postHoles(id, f); });
  applyHighlights();
  renderThreadChips();
  positionPopover();
  renderHolePop();
}

/* A bare block leaves out the number and the title (the description of an item: its
   item entry shows both) and keeps everything else. */
function sectionBlock(s, { bare = false } = {}) {
  const body = el("div", { class: "body" });
  const written = s.id in state.sections;
  if (written && state.sections[s.id].kind === "html") body.append(el("div", { class: "frame-slot", "data-frame": s.id }));
  else if (written) body.innerHTML = state.sections[s.id].html;
  else if (writingId() === s.id) body.append(el("p", { class: "writing-line", text: "writing" }));
  const cls = ["sec", written ? "" : "unwritten", written && state.sections[s.id].kind === "html" ? "html" : "", isUpdated(s.id) ? "updated" : "", bare ? "bare" : ""].join(" ");
  return el("section", { class: cls, id: `sec-${s.id}`, "data-id": s.id },
    el("h2", {},
      ...(bare ? [] : [el("span", { class: "num", text: numberOf(s.id) }), " ", s.title]),
      el("span", { class: "t-chips", "data-section": s.id }),
      isUpdated(s.id)
        ? el("button", { class: "badge new", text: "updated · mark read", title: "Mark this section as read: its highlights go away",
                         onclick: (e) => { e.stopPropagation(); markSeen([s.id]); } })
        : null,
      el("button", { class: "sec-comment", text: "+ comment section", title: "Comment on the whole section",
                     onclick: () => openComposer({ section: s.id, quote: "", prefix: "" }) }),
      el("button", { class: "sec-comment ask", text: "ask", title: "Open a side thread about this section",
                     onclick: () => openComposer({ section: s.id, quote: "", prefix: "" }, "ask") })),
    body,
    ...(written && sectionQuestions(s.id).length
      ? [isScopingSection(s) ? holeIndex(s.id)
        : el("div", { class: "sec-questions" }, ...sectionQuestions(s.id).map(questionCard),
             ...(paused() ? [goOnButton()] : []))] : []));
}

/* The scoping's two buttons, under the hole index at the end of the scoping tab, while scoping
   runs on a drawing: « What's missing? » (a batch whose action is "missing": the scoper
   reads the drawing again, and opens holes or suppositions, or says nothing is left) and
   « End scoping » (action "end-scoping": the planner converts the drawing into the outline
   and the lexicon, then the writer writes the model). « End scoping » waits until no hole
   is open; the server refuses it otherwise. Both take the draft comments with them, and
   hide once « End scoping » is sent, until the status moves. */
const sentSince = (action) => {
  const b = lastBatchOf(action);
  return !!b.sent && b.sent >= (state.status.since || "");
};
const openHoles = () => openQuestions().filter((q) => q.section && inScoping(q.section));

function scopingActions() {
  if (!drawingScoping() || sentSince("end-scoping")) return null;
  const n = openHoles().length;
  return el("div", { class: "scoping-actions" },
    el("button", { class: "btn", text: "What's missing?",
                   title: "The scoper reads the drawing again: it opens holes or suppositions, or says nothing is left",
                   onclick: (e) => send("missing", e.currentTarget) }),
    el("button", { class: "btn primary", text: "End scoping", disabled: n > 0,
                   title: n ? `${n} hole${n > 1 ? "s" : ""} still open: answer ${n > 1 ? "them" : "it"} first`
                     : "The planner converts the drawing into the outline and the lexicon, then the writer writes the model",
                   onclick: (e) => send("end-scoping", e.currentTarget) }));
}

/* The holes message (page -> frame): the open holes of a scoping section that name an
   element of the drawing (`element`, an id in the HTML), which the frame marks. A hole's
   element chip reveals the element (« reveal-element »), the frame answering « revealed »
   as for a passage. */
function postHoles(id, f = frames.get(id)) {
  if (!f || !f.contentWindow || !state || !inScoping(id)) return;
  const holes = openQuestions().filter((q) => q.section === id && q.element)
    .map((q) => ({ element: q.element, question: q.id }));
  f.contentWindow.postMessage({ viewConcept: "holes", holes }, "*");
}
// `holes`: the questions whose boxes open on the element once it is shown (a line of the
// hole index), or none (a box's element chip).
function revealElement(id, element, holes = null) {
  setTab(tabOf(id));
  const f = frames.get(id);
  if (!f || !f.contentWindow) {
    scrollToSection(id);
    if (holes) openHolePop(id, holes, { line: holes[0] });
    return;
  }
  revealing.set(id, { element, holes });
  f.contentWindow.postMessage({ viewConcept: "reveal-element", element }, "*");
}

/* ---------------- the hole popover ----------------
   A hole's box opens on the element of the drawing it bears on, not in a list: a click on
   an element the frame marks (the hole click) opens the boxes of the open questions on
   that element in a popover beside it, as a side thread opens on its passage, and a click
   elsewhere in the drawing, outside the popover or Escape closes it. The end of the
   scoping section keeps an index, one line per open hole (its id, its element, the start
   of its text): a click on a line shows the element and opens the popover there, so a
   hole whose element the drawing no longer has still opens, on its line. A question on
   the scoping section that names no element keeps its box in the index. The popover
   closes once none of its questions is open; it docks across the bottom in the narrow
   layout, as the thread popover does. */
let holePop = null; // { section, questions: [ids], anchor: { f, rect } (in the frame's viewport) | { line: question id } }

function holeIndex(id) {
  const line = (q) => {
    const on = openQuestions().filter((o) => o.section === id && o.element === q.element).map((o) => o.id);
    return el("button", {
      class: `hole-line ${holePop && holePop.questions.includes(q.id) ? "open" : ""}`, "data-question": q.id,
      title: "Show this hole in the drawing and answer it there",
      onclick: (e) => { e.stopPropagation(); revealElement(id, q.element, on); } },
      el("span", { class: "num", text: q.id }),
      q.kind === "supposition" ? el("span", { class: "badge tone-info", text: "supposition" }) : null,
      el("span", { class: "badge accent", text: q.element }),
      el("span", { class: "hole-text", text: q.text }));
  };
  return el("div", { class: "sec-questions hole-index" },
    ...sectionQuestions(id).map((q) => (q.element ? line(q) : questionCard(q))));
}

function openHolePop(section, questions, anchor) {
  holePop = { section, questions, anchor };
  renderHolePop();
  document.querySelectorAll(".hole-line").forEach((b) => b.classList.toggle("open", questions.includes(b.dataset.question)));
}

function closeHolePop() {
  holePop = null;
  $("#hole-pop").hidden = true;
  document.querySelectorAll(".hole-line.open").forEach((b) => b.classList.remove("open"));
}

function renderHolePop() {
  const pop = $("#hole-pop");
  if (!holePop) return;
  const open = openQuestions().filter((q) => holePop.questions.includes(q.id));
  if (!open.length) { closeHolePop(); return; }
  const head = el("div", { class: "t-title" },
    el("span", { class: "dim", text: `hole${open.length > 1 ? "s" : ""} · ${open[0].element || ""}` }),
    el("button", { class: "t-close", text: "×", title: "Close (Esc)", onclick: closeHolePop }));
  const cards = open.map(questionCard);
  // Re-attaching a box would blur its text field: only when the boxes changed.
  const same = cards.length === pop.children.length - 1 && cards.every((c, i) => pop.children[i + 1] === c);
  if (!same) pop.replaceChildren(head, ...cards);
  pop.hidden = false;
  positionHolePop();
}

function holeAnchorRect() {
  // A frame drawn again (the scoper redrew) loses the element's place: the line holds it.
  const a = holePop.anchor;
  if (a.f && a.f.isConnected) return pageRect(a.f, a.rect);
  const line = document.querySelector(`.hole-line[data-question="${CSS.escape(a.line || holePop.questions[0])}"]`);
  return line ? line.getBoundingClientRect() : null;
}

function positionHolePop() {
  const pop = $("#hole-pop");
  if (!holePop || pop.hidden || isNarrow()) return;
  const r = holeAnchorRect();
  const visible = r && r.bottom > 0 && r.top < innerHeight;
  pop.style.visibility = visible ? "visible" : "hidden";
  if (!visible) return;
  const h = pop.offsetHeight;
  const w = pop.offsetWidth;
  const below = r.bottom + 6;
  const top = below + h <= innerHeight - 8 || r.top - h - 6 < 8 ? below : r.top - h - 6;
  pop.style.top = `${Math.max(8, Math.min(top, innerHeight - h - 8))}px`;
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
}

/* The hole click message: the questions of the hole element clicked and where it sits, or
   none for a click elsewhere in the drawing. */
function frameHoleClick(id, f, d) {
  const questions = Array.isArray(d.questions) ? d.questions.map(String) : [];
  if (!questions.length || !d.rect) { closeHolePop(); return; }
  openHolePop(id, questions, { f, rect: d.rect });
}

document.querySelectorAll(".view").forEach((v) => v.addEventListener("scroll", positionHolePop, { passive: true }));
addEventListener("resize", positionHolePop);
document.addEventListener("mousedown", (e) => {
  if (holePop && !e.target.closest("#hole-pop, #composer, #thread-pop, .hole-line")) closeHolePop();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && holePop && !e.target.closest("#composer")) closeHolePop();
});

/* ---------------- the Doc tab ----------------
   The repo docs the branch concerns (`state.docs`, from the server): the doc set, the list
   of docs an agent keeps (path, the reason it is listed, its count of stale passages),
   commentable as the section DOC_SET ("doc:"); under it a bar of doc titles, and one doc shown at
   a time. The doc shown is a doc section: the file read from the worktree, drawn as a
   section block (`section: "doc:<path>"`) that is commented, asked about and highlighted
   like a section of the model, with « updated · mark read » on the key "doc:<path>". A title
   in the bar carries a green dot when its doc was rewritten since its highlight baseline.
   Two marks: the green bar and words of the change highlights (markUpdates), and the base
   mark, a bar in the right margin of every block whose text is not among the blocks of the
   doc at the merge base (`base_html`), every block for a doc created on the branch (`new`),
   and in a doc the base had, a blue background on the words it added (markBase). A doc
   the code moved with its folder (`from`, its old path, shown « moved from » in the doc
   set list) is compared with the old doc at its old path. Stale passages get a wavy underline whose
   hover shows the note (applyHighlights, "stale passages"). Lexicon terms are underlined,
   none as its definition: the model's lexicon, or in a docs review the reference model's
   (annotateDocTerms). Relative images and links load from the worktree,
   /s/<slug>/repo/<doc dir>/<relative>. A docs review adds its agent questions (the scope
   block) above the doc set, and « Create PR » at the end. « edit » in a doc's heading
   swaps its text for its Markdown in a text box (see "editing a doc"). While the doc in
   sight is a README.md (in the worktree or missing), a line of its own under the bar of
   doc titles holds « rewrite <path> with write-readme »: it sends a rewrite request (a
   batch whose action is "rewrite-readme", carrying the path) at once, with the drafts.
   While the repo lexicon (REPO_LEXICON) is in the doc set and missing from the worktree,
   its doc set entry holds « write repo lexicon », which sends a "write-lexicon" batch the
   same way.
   The docs come in the write order. The doc set list shows the review list first, the
   docs the user is asked to read: every doc but the minor ones (`minor`, the reason the
   doc pass gave), and a minor doc on which a stale passage is shown, which climbs back.
   The other minor docs sit in a fold « n minor docs », each with its reason and its diff
   size `+a −r`. The bar of doc titles follows the same order, the minor docs after the
   review list, set back. A README with a failure indicator (`failing`) shows « n/total
   failing » in the list; when more than REWRITE_HINT of its passages fail, or its
   structure fails, its rewrite button is put forward (accent).
   A README lists its missing facts under its text (`state.docs.facts`), what its old text
   said and no README written says any more, after a full rewrite, a restructuring or a
   folder model rewritten in full: each fact with the agent's proposal, its reason and its
   state. A fact is commented like a passage of the doc: its comment is anchored to
   "doc:<path>", quotes the fact and carries its id (`fact`); a passage selected in a fact
   anchors the same way. A fact new
   or changed since the baseline "facts:<path>" gets the green bar, and « mark read » on
   the README marks its facts read too.
   The concept triage (`state.docs.triage`), when the agent wrote one, is a table above the
   doc set list: one row per concept of the model, the reason (who ignores it gets what
   wrong) and whether it enters the docs. Each row has « + comment » and « ask », anchored
   to "triage:<id>" with the concept as quote; a row new or changed since the baseline
   "triage:" gets the green bar, and « mark read » on the table moves the baseline.
   Under it, the move plan of each restructured README (`state.docs.moves`), one table per
   README: each passage of its folder model (the README's skeleton is never in a plan), the
   README it goes to and what it becomes there. Its rows are commented like the triage's, on
   "moves:<id>" with the passage as quote, against the baseline "moves:<path>". While the
   doc pass waits on the plans ("awaiting-moves", document-feature's folder models held),
   « Write READMEs » sits under them. */

let shownDoc = null; // path of the doc shown in the Doc tab
const REPO_LEXICON = ".agents/lexicon.md"; // store.py's REPO_LEXICON
// The failing share of a README's passages beyond which its rewrite button is put forward.
const REWRITE_HINT = 0.5;
let minorOpen = false; // the fold of the minor docs is open (kept across renders)

function renderDocTab(ending) {
  const view = $("#doc");
  const docs = docsOf();
  // In a docs review the scope block (its agent questions) sits at the top of the Doc tab.
  const top = isDocsReview() ? [$("#scope")] : [];
  if (!docs.set.length) {
    view.replaceChildren(...top, triageBlock(docs), ...moveBlocks(docs), movesButton, isDocsReview() ? el("p", { class: "dim empty", text: "Waiting for the doc set…" }) : "", ...ending);
    return;
  }
  if (!docs.set.some((d) => d.path === shownDoc)) shownDoc = reviewOrder(docs)[0].path;
  const entry = docs.set.find((d) => d.path === shownDoc);
  view.replaceChildren(...top, triageBlock(docs), ...moveBlocks(docs), movesButton, docSetBlock(docs), docBar(docs), docRewrite(shownDoc, entry),
    docBlock(shownDoc, docs.views[shownDoc] || {}), ...ending);
}

const staleCount = (docs, d) => d.stale ?? docs.stale.filter((s) => s.doc === d.path).length;
const staleBadge = (n) => (n ? el("span", { class: "badge tone-warn", text: `${n} stale` }) : null);
const missingBadge = (v) => (v.exists === false ? el("span", { class: "badge", text: "missing" }) : null);
// A minor doc stays out of the review list, unless a stale passage is shown on it or a
// missing fact of it waits for your decision.
const isFolded = (docs, d) => !!d.minor && !staleCount(docs, d) && !d.pending;
// Why a minor doc is back in the review list.
const liftedBy = (docs, d) => [staleCount(docs, d) ? "a stale passage" : "", d.pending ? "a pending missing fact" : ""]
  .filter(Boolean).join(" and ");
// The docs in the write order, the review list first, then the folded minor docs.
const reviewOrder = (docs) => [...docs.set.filter((d) => !isFolded(docs, d)), ...docs.set.filter((d) => isFolded(docs, d))];
const diffText = (d) => `+${(d.diff || {}).added ?? 0} −${(d.diff || {}).removed ?? 0}`;
// The failure indicator of a README write-readme edited.
const failingBadge = (d) => {
  const f = d.failing;
  if (!f) return null;
  return el("span", { class: `badge ${rewriteHinted(d) ? "tone-warn" : ""}`,
                      text: `${f.fail}/${f.total} failing${f.structure ? " · structure fails" : ""}`,
                      title: "The passages of the README's skeleton that failed write-readme's checks before its edit, out of all of them" });
};
const rewriteHinted = (d) => !!(d && d.failing && (d.failing.structure || d.failing.fail > REWRITE_HINT * d.failing.total));
// The missing facts of README `path`, [] for a doc without.
const factsOf = (path) => ((docsOf().facts || {})[path] || {}).list || [];
const factsUpdated = (path) => factsOf(path).some((f) => f.updated);
// The title of a doc's dot in the bar of titles: what changed since the last batch.
const dotTitle = (rewritten, facts) =>
  rewritten && facts ? "Rewritten, and a missing fact changed, since your last batch"
    : facts ? "A missing fact changed since your last batch" : "Rewritten since your last batch";
const factsBadge = (d) => (d.facts ? el("span", { class: "badge alt", text: `${d.facts} missing facts` }) : null);

// The heading of a doc set or doc block: its label, its thread chips, then « mark read »
// when updated and the comment buttons, as in a section block.
function docHeading(id, label, updated, what, edit = null) {
  return el("h2", {}, label,
    el("span", { class: "t-chips", "data-section": id }),
    updated
      ? el("button", { class: "badge new", text: "updated · mark read", title: `Mark this ${what} as read: its highlights go away`,
                       onclick: (e) => { e.stopPropagation(); markSeen([id]); } })
      : null,
    el("button", { class: "sec-comment", text: `+ comment ${what}`, title: `Comment on the whole ${what}`,
                   onclick: () => openComposer({ section: id, quote: "", prefix: "" }) }),
    el("button", { class: "sec-comment ask", text: "ask", title: `Open a side thread about this ${what}`,
                   onclick: () => openComposer({ section: id, quote: "", prefix: "" }, "ask") }),
    edit);
}

// A commentable row of a Doc tab table: `anchor` its comment anchor, `quote` what a
// comment on it quotes, `what` how its buttons name it.
function rowButtons(anchor, quote, what) {
  const target = (e) => ({ section: anchor, quote, prefix: "", rect: e.currentTarget.getBoundingClientRect() });
  return el("td", { class: "row-actions" },
    el("button", { class: "sec-comment", text: "+ comment", title: `Comment on this ${what}`, onclick: (e) => openComposer(target(e)) }),
    el("button", { class: "sec-comment ask", text: "ask", title: `Open a side thread about this ${what}`, onclick: (e) => openComposer(target(e), "ask") }));
}

// The heading of a Doc tab table: its title, then « mark read » while a row is updated
// (the baseline `key` moves to `text`).
function tableHeading(title, tip, key, text, updated) {
  return el("h2", { title: tip }, title,
    updated
      ? el("button", { class: "badge new", text: "updated · mark read", title: "Mark this table as read: its highlights go away",
                       onclick: (e) => { e.stopPropagation(); markRead({ [key]: text }); } })
      : null);
}

function triageBlock(docs) {
  const { list, text } = docs.triage;
  if (!list.length) return "";
  const row = (r) => el("tr", { id: `sec-${TRIAGE_PREFIX}${r.id}`, class: r.updated ? "updated" : "", "data-anchor": TRIAGE_PREFIX + r.id },
    el("td", { class: "row-quote", text: r.concept }),
    el("td", { text: r.reason }),
    el("td", {}, el("span", { class: `badge ${r.enters ? "tone-ok" : ""}`, text: r.enters ? "yes" : "no" })),
    rowButtons(TRIAGE_PREFIX + r.id, r.concept, "concept"));
  return el("section", { class: "sec doc-table-sec", id: "sec-triage" },
    tableHeading("concept triage", "Whether each concept of the model enters the docs: who uses what its folder gives out or exposes, and ignores it, gets something wrong",
                 TRIAGE_PREFIX, text, list.some((r) => r.updated)),
    el("div", { class: "body" }, el("table", { class: "doc-table" },
      el("thead", {}, el("tr", {}, ...["concept", "who ignores it gets it wrong?", "enters the docs", ""].map((h) => el("th", { text: h })))),
      el("tbody", {}, ...list.map(row)))));
}

function moveBlocks(docs) {
  return Object.entries(docs.moves).map(([path, { list, text }]) => {
    const row = (r) => el("tr", { id: `sec-${MOVES_PREFIX}${r.id}`, class: r.updated ? "updated" : "", "data-anchor": MOVES_PREFIX + r.id },
      el("td", { class: "row-quote", text: r.passage }, r.note ? el("div", { class: "dim row-note", text: r.note }) : null),
      el("td", {}, r.to ? el("code", { text: r.to }) : el("span", { class: "dim", text: "—" })),
      el("td", {}, el("span", { class: `badge ${r.becomes === "nowhere" ? "tone-flag" : ""}`, text: r.becomes })),
      rowButtons(MOVES_PREFIX + r.id, r.passage, "passage"));
    return el("section", { class: "sec doc-table-sec", id: `sec-moves-${path}` },
      tableHeading(el("span", {}, "move plan · ", el("code", { text: path })), "Where each passage of this README's folder model goes: the doc pass writes the folder models from this plan",
                   MOVES_PREFIX + path, text, list.some((r) => r.updated)),
      el("div", { class: "body" }, el("table", { class: "doc-table" },
        el("thead", {}, el("tr", {}, ...["passage", "goes to", "becomes", ""].map((h) => el("th", { text: h })))),
        el("tbody", {}, ...list.map(row)))));
  });
}

// The old path of a doc the code moved with its folder: its base mark reads the doc there.
const movedFrom = (d) => (d.from ? el("span", { class: "dim doc-moved", text: ` · moved from ${d.from}`,
                                                 title: "The code moved this doc: its blue bar compares it with the old doc at its old path" }) : null);

function docSetBlock(docs) {
  const item = (d) => el("li", {},
    el("button", { class: "doc-open", text: d.path, title: "Show this doc", onclick: () => openDoc(d.path) }),
    d.reason ? ` — ${d.reason}` : "", movedFrom(d),
    d.minor && !isFolded(docs, d) ? el("span", { class: "badge", text: `minor · ${diffText(d)}`, title: `Minor: ${d.minor}. ${liftedBy(docs, d).replace(/^./, (c) => c.toUpperCase())} brought it back to the review list` }) : null,
    staleBadge(staleCount(docs, d)), failingBadge(d), factsBadge(d), missingBadge(docs.views[d.path] || {}),
    lexiconButton(d.path, docs.views[d.path] || {}));
  const minor = docs.set.filter((d) => isFolded(docs, d));
  const fold = minor.length
    ? el("details", { class: "doc-minor", ...(minorOpen ? { open: "" } : {}),
                      ontoggle: (e) => { minorOpen = e.currentTarget.open; } },
        el("summary", { text: `${minor.length} minor doc${minor.length > 1 ? "s" : ""}` }),
        el("ul", { class: "doc-set" }, ...minor.map((d) => el("li", {},
          el("button", { class: "doc-open", text: d.path, title: "Show this doc", onclick: () => openDoc(d.path) }),
          ` — minor: ${d.minor}`, movedFrom(d), el("span", { class: "doc-diff", text: diffText(d), title: "Its diff size: lines added and removed" }),
          failingBadge(d), factsBadge(d), missingBadge(docs.views[d.path] || {})))))
    : null;
  return el("section", { class: "sec doc-set-sec", id: `sec-${DOC_SET}`, "data-id": DOC_SET },
    docHeading(DOC_SET, "doc set", false, "doc set"),
    el("div", { class: "body" }, el("ul", { class: "doc-set" }, ...docs.set.filter((d) => !isFolded(docs, d)).map(item)), fold,
      docs.removed.length ? el("p", { class: "dim doc-removed", text: `removed by you: ${docs.removed.join(", ")}` }) : null));
}

function docBar(docs) {
  return el("div", { class: "doc-bar" }, ...reviewOrder(docs).map((d) => {
    const v = docs.views[d.path] || {};
    const folded = isFolded(docs, d);
    return el("button", { class: `doc-title ${d.path === shownDoc ? "active" : ""} ${v.exists === false ? "missing" : ""} ${folded ? "minor" : ""}`,
                          title: folded ? `minor: ${d.minor} (${diffText(d)})` : d.reason || d.path, onclick: () => openDoc(d.path) },
      v.updated || factsUpdated(d.path) ? el("span", { class: "doc-dot", title: dotTitle(v.updated, factsUpdated(d.path)) }) : null,
      d.path, staleBadge(staleCount(docs, d)),
      docEdit && docEdit.path === d.path ? el("span", { class: "badge", text: "editing", title: "Your edit of this doc is not saved yet" }) : null);
  }));
}

// « write repo lexicon »: on the repo lexicon's doc set entry, while it is missing.
function lexiconButton(path, v) {
  if (path !== REPO_LEXICON || v.exists !== false) return null;
  return el("button", { class: "btn doc-lexicon", text: "write repo lexicon",
                        title: "Ask the agent that owns the docs to write the repo lexicon (your drafts go with it)",
                        onclick: (e) => send("write-lexicon", e.currentTarget) });
}

// The rewrite request's line: drawn only while the doc in sight is named README.md; put
// forward when its failure indicator passes REWRITE_HINT or its structure fails.
function docRewrite(path, entry) {
  if (path.split("/").pop() !== "README.md") return "";
  const hinted = rewriteHinted(entry);
  return el("div", { class: "doc-rewrite" },
    el("button", { class: `btn ${hinted ? "primary" : ""}`, text: `rewrite ${path} with write-readme`,
                   title: "Ask the agent that owns the docs to write this README again with write-readme (your drafts go with it)",
                   onclick: (e) => send("rewrite-readme", e.currentTarget, { path }) }),
    hinted ? el("span", { class: "dim doc-rewrite-why", text: ` ${failingWhy(entry.failing)}` }) : null);
}
const failingWhy = (f) => (f.structure ? "its structure fails" : `${f.fail} of its ${f.total} passages fail`);

/* The missing facts of a README, under its text (after a full rewrite, a restructuring or
   a folder model rewritten in full): each fact with its old passage, the agent's proposal
   and reason, and its state; « + comment » and « ask » open the composer on the fact, as
   on a passage of the doc. */
const FACT_STATE = { pending: "waits on you", kept: "kept", left: "left" };
const FACT_PROPOSAL = { keep: "keep", leave: "leave" };
function docFacts(path) {
  const facts = factsOf(path);
  if (!facts.length) return null;
  const id = DOC_PREFIX + path;
  const target = (f) => ({ section: id, quote: f.fact, prefix: "", fact: f.id });
  return el("div", { class: "doc-facts", "data-doc": path },
    el("h3", { text: `${facts.length} missing fact${facts.length > 1 ? "s" : ""}`,
               title: "What the old README said and no README written says any more, after a full rewrite, a restructuring or a folder model rewritten in full; a fact you do not comment on is not taken back" }),
    el("ul", {}, ...facts.map((f) => el("li", { class: `doc-fact state-${f.state} ${f.updated ? "updated" : ""}`, "data-fact": f.id },
      el("span", { class: "fact-text", text: f.fact }),
      f.passage ? el("span", { class: "dim", text: ` (passage ${f.passage})` }) : null,
      el("div", { class: "fact-meta" },
        el("span", { class: `badge ${f.proposal === "keep" ? "tone-ok" : "tone-flag"}`, text: FACT_PROPOSAL[f.proposal] || f.proposal }),
        el("span", { class: "dim", text: ` ${f.reason}` }),
        el("span", { class: `badge ${f.state === "pending" ? "tone-warn" : ""}`, text: FACT_STATE[f.state] || f.state }),
        el("button", { class: "sec-comment", text: "+ comment", title: "Comment on this fact: « keep it », « leave it », or a question",
                       onclick: (e) => openComposer({ ...target(f), rect: e.currentTarget.getBoundingClientRect() }) }),
        el("button", { class: "sec-comment ask", text: "ask", title: "Open a side thread about this fact",
                       onclick: (e) => openComposer({ ...target(f), rect: e.currentTarget.getBoundingClientRect() }, "ask") }))))));
}

function docBlock(path, v) {
  const id = DOC_PREFIX + path;
  const body = el("div", { class: "body" });
  const editor = v.exists && docEditor(path, v);
  if (editor) body.append(editor);
  else if (v.exists) {
    body.innerHTML = v.html || "";
    resolveRepoLinks(body, path);
  } else body.append(el("p", { class: "dim", text: "Missing: this doc is not in the worktree." }));
  const edit = v.exists && !editor
    ? el("button", { class: "sec-comment", text: "edit", title: "Edit this doc's Markdown by hand", onclick: () => startDocEdit(path) })
    : null;
  const updated = !!v.updated || factsUpdated(path);
  return el("section", { class: `sec doc-sec ${v.exists ? "" : "missing"} ${updated ? "updated" : ""}`, id: `sec-${id}`, "data-id": id },
    docHeading(id, el("code", { text: path }), updated && !editor, "doc", edit), body, docFacts(path));
}

/* ---------------- editing a doc ----------------
   « edit » opens the doc's Markdown (`md`, the file as read) in a text box in place of its
   text; « save » writes it to the worktree (POST /api/s/<slug>/doc, with the text the edit
   started from). The box is one element kept across renders, so a re-render while you type
   (an agent run, a thread) keeps your text, its caret and its scroll. When the file changes
   meanwhile, a notice says so and « save » becomes « save anyway », which overwrites that
   change; the server refuses a save whose starting text is no longer the file's, so only a
   change you were told of is overwritten. ⌘↵ saves, Esc cancels (asking first when the
   text was changed). Your own words get no green highlight. One doc is edited at a time;
   its title in the bar says « editing » while the edit is not saved. */
let docEdit = null; // { path, base (the text the edit started from), box, ta, note, save }

function startDocEdit(path) {
  const v = docsOf().views[path];
  if (!v || !v.exists) return;
  if (docEdit && docEdit.path !== path && docEdit.ta.value !== docEdit.base &&
      !confirm(`Drop your unsaved edit of ${docEdit.path}?`)) return;
  const ta = el("textarea", { class: "doc-edit-text", spellcheck: "true" });
  ta.value = v.md || "";
  const note = el("p", { class: "doc-edit-note", hidden: true,
                         text: "The file changed since you started editing: saving overwrites that change." });
  const save = el("button", { class: "btn primary", text: "save", title: "Write the doc to the worktree (⌘↵)", onclick: saveDocEdit });
  const cancel = el("button", { class: "btn", text: "cancel", title: "Drop your edit (Esc)", onclick: cancelDocEdit });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveDocEdit(); }
    else if (e.key === "Escape") { e.preventDefault(); cancelDocEdit(); }
  });
  const box = el("div", { class: "doc-editor" }, ta, note, el("div", { class: "doc-edit-actions" }, save, cancel));
  docEdit = { path, base: v.md || "", box, ta, note, save };
  releaseAnchor();
  renderSections();
  ta.focus({ preventScroll: true });
  ta.setSelectionRange(0, 0);
}

// The editor of doc `path` with its notice brought up to date, or null when it is not edited.
function docEditor(path, v) {
  if (!docEdit || docEdit.path !== path) return null;
  const changed = (v.md || "") !== docEdit.base;
  docEdit.note.hidden = !changed;
  docEdit.save.textContent = changed ? "save anyway" : "save";
  return docEdit.box;
}

async function saveDocEdit() {
  if (!docEdit) return;
  const edit = docEdit;
  const v = docsOf().views[edit.path];
  if (!v || !v.exists) { toast(`${edit.path} is no longer in the worktree`); return; }
  // « save anyway »: the file as the page last read it, which the notice told of.
  const base = v.md || "";
  edit.save.disabled = true;
  try {
    await postJSON(`/api/s/${SLUG}/doc`, { path: edit.path, md: edit.ta.value, base });
  } catch (e) {
    toast(`Could not save: ${e.message}`);
    edit.save.disabled = false;
    await load();
    return;
  }
  if (docEdit === edit) docEdit = null;
  toast("Doc saved");
  await load();
}

function cancelDocEdit() {
  if (!docEdit) return;
  if (docEdit.ta.value !== docEdit.base && !confirm("Drop your edit?")) return;
  docEdit = null;
  renderSections();
}


/* A doc gives its images and links by a path relative to its own folder: they load from
   the worktree through the server. An absolute URL, a root path or an anchor stays. */
function resolveRepoLinks(body, path) {
  const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "";
  const resolve = (raw) => {
    if (!raw || /^([a-z][\w+.-]*:|\/|#)/i.test(raw)) return null;
    const u = new URL(raw, `http://repo/${dir}`);
    return `/s/${encodeURIComponent(SLUG)}/repo${u.pathname}${u.search}${u.hash}`;
  };
  body.querySelectorAll("img[src]").forEach((img) => {
    const r = resolve(img.getAttribute("src"));
    if (r) img.setAttribute("src", r);
  });
  body.querySelectorAll("a[href]").forEach((a) => {
    const r = resolve(a.getAttribute("href"));
    if (r) { a.setAttribute("href", r); a.target = "_blank"; a.rel = "noopener"; }
  });
}

// Shows the doc `path` in the Doc tab, from its top.
function openDoc(path) {
  if (path === shownDoc) return;
  shownDoc = path;
  releaseAnchor();
  renderSections();
  const b = document.getElementById(`sec-${DOC_PREFIX}${path}`);
  const view = $("#doc");
  if (b && b.getBoundingClientRect().top < view.getBoundingClientRect().top) view.scrollTop += b.getBoundingClientRect().top - view.getBoundingClientRect().top - 40;
  savePosition();
}

/* Opens the tab of section `id`; for a doc, the Doc tab on that doc. Following a comment or
   a side thread anchored in another doc opens that doc. */
function openSection(id) {
  if (tab !== tabOf(id)) setTab(tabOf(id));
  const path = docPathOf(id);
  if (path !== null && path !== shownDoc && docsOf().set.some((d) => d.path === path)) {
    shownDoc = path;
    releaseAnchor();
    renderSections();
    savePosition();
  }
}

// The lexicon underlined in the docs: the model's, or the reference model's in a docs review.
const docLexicon = () => (isDocsReview() ? ((docsOf().reference || {}).lexicon || []) : state.plan.lexicon);
// The lexicon a term span's index points into (data-lex="ref": the reference model's).
const lexiconOf = (n) => (n.dataset.lex === "ref" ? ((docsOf().reference || {}).lexicon || []) : state.plan.lexicon);

/* Every occurrence of a lexicon term in the doc shown gets the plain underline and its tip;
   none is marked as its definition, which stays in the term's home section. */
function annotateDocTerms(view) {
  const body = view.querySelector(".doc-sec .body");
  if (!body) return;
  const ref = isDocsReview();
  docLexicon().forEach((t, i) => wrapTerm(body, t.term, () =>
    el("span", { class: "term", "data-term": i, ...(ref ? { "data-lex": "ref" } : {}) })));
}

/* ---------------- stale passages ----------------
   A stale passage is a passage of a doc that the model contradicts, flagged by an agent
   (`state.docs.stale`: doc, quote, the section it contradicts, a note). The quote is the
   text as in the file: found in the doc shown as is, else with its Markdown marks taken
   out. It gets a wavy underline (a highlight, so it may run across words of any markup),
   and the pointer over it, or a tap, shows the note. */
let staleRanges = []; // [entry, range] of every stale passage found in the doc shown

function findStale(s) {
  const id = DOC_PREFIX + s.doc;
  const plain = String(s.quote || "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[`*]/g, "");
  return findQuote(id, s.quote, "") || findQuote(id, plain, "");
}

function staleAt(x, y) {
  for (const [s, r] of staleRanges) {
    for (const b of r.getClientRects()) {
      if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) return [s, b];
    }
  }
  return null;
}

function staleNote(s) {
  const sec = s.section || "";
  const where = !sec ? "" : state.plan.outline.some((o) => o.id === sec) ? `§${numberOf(sec)} ${titleOf(sec)}` : sec;
  return `stale${where ? ` · contradicts ${where}` : ""}${s.note ? ` — ${s.note}` : ""}`;
}

let staleTip = false; // the tip shows a stale passage's note
$("#doc").addEventListener("mousemove", (e) => {
  if (isTouch() || e.target.closest("[data-tip], [data-term]")) return;
  const hit = staleAt(e.clientX, e.clientY);
  if (hit) { showTip(staleNote(hit[0]), null, hit[1]); staleTip = true; }
  else if (staleTip) { $("#tip").hidden = true; staleTip = false; }
});

/* ---------------- the code tab ----------------
   A refactor section that carries item fields ("item": {files, verdict, batch?,
   implements, note, relations}) is an item: one unit of the diff, a file or files doing
   one job, judged against the model. The items are drawn as the review table: one item
   entry per item (its title and files, its verdict, its batch when any item has one, the
   concepts it implements, a note), the items that need action first. Clicking an entry opens its description underneath, which is
   the section's own block, so comments, threads, highlights and annotations work there
   as in the explanation. Below the table, the structure view (see structureView). The
   to-do list of a feature (the section "todo": the work that holds no decision of
   the user's, written with the model) comes above the table; the other refactor sections,
   such as the applied changes, follow it as plain sections. A review whose refactor
   sections carry no item fields is drawn as plain sections only. */

// Verdict keys in table order (the session workflow's list in verdicts.yaml, sent with the
// state): those that need action first, the one that needs none (« conforms », « keep ») last.
const verdictKeys = () => (state.verdicts || []).map((v) => v.key);
// The tone a verdict is drawn in (ok, danger, warn, alt, flag, info), "" for an unknown verdict.
const TONES = ["ok", "danger", "warn", "alt", "flag", "info"];
const toneOf = (v) => {
  const tone = ((state.verdicts || []).find((d) => d.key === v) || {}).tone;
  return TONES.includes(tone) ? tone : "";
};
const openItems = new Set(); // ids of the items whose description is open, across re-renders

const isItem = (s) => !!s && !!s.item && typeof s.item === "object";
const isFinding = (s) => !isItem(s) && s.kind === "finding";
const verdictOf = (s) => String(s.item.verdict || "no verdict");
// A batch is a short label or number grouping items, e.g. the PR they go into.
const hasBatch = (s) => s.item.batch != null && String(s.item.batch).trim() !== "";
// An unknown verdict sorts after the known ones that need action, before the last one.
const verdictRank = (v) => {
  const keys = verdictKeys();
  return keys.includes(v) ? keys.indexOf(v) : keys.length - 1.5;
};
const lexiconIndex = (name) =>
  state.plan.lexicon.findIndex((t) => t.term.toLowerCase() === String(name).toLowerCase());

function refactorTab(sections) {
  const items = sections.filter(isItem);
  if (!items.length) return sections.map((s) => sectionBlock(s));
  const findings = sections.filter(isFinding);
  const rest = sections.filter((s) => !isItem(s) && !isFinding(s));
  const block = (s) => {
    const b = sectionBlock(s);
    b.classList.add("rv-after"); // aligned on the table, see app.css
    return b;
  };
  const before = rest.filter((s) => s.id === "todo").map(block);
  const after = rest.filter((s) => s.id !== "todo").map(block);
  return [...before, reviewTable(items), structureView(items, findings), ...after].filter(Boolean);
}

function verdictBadge(v) {
  return el("span", { class: `badge verdict ${toneOf(v) ? `tone-${toneOf(v)}` : ""}`, text: v });
}

function fileRef(f) {
  const href = vscodeHref(f);
  return href
    ? el("a", { class: "cite", href, title: "Open in VS Code", onclick: (e) => e.stopPropagation() }, el("code", { text: f }))
    : el("code", { text: f });
}

function reviewTable(items) {
  const sorted = items.map((s, i) => [s, i])
    .sort(([a, i], [b, j]) => verdictRank(verdictOf(a)) - verdictRank(verdictOf(b)) || i - j)
    .map(([s]) => s);
  const counts = new Map();
  for (const s of sorted) counts.set(verdictOf(s), (counts.get(verdictOf(s)) || 0) + 1);
  const summary = [`${items.length} item${items.length > 1 ? "s" : ""}`, ...[...counts].map(([v, n]) => `${n} ${v}`)];
  const batched = items.some(hasBatch);
  const columns = ["item", "verdict", ...(batched ? ["batch"] : []), "implements", "note"];
  return el("div", { class: "rv rv-wide" },
    el("div", { class: "rv-head" }, "review table", el("span", { class: "rv-counts", text: summary.join(" · ") })),
    el("div", { class: "rv-scroll" },
      el("table", { class: "rv-table" },
        el("thead", {}, el("tr", {}, ...columns.map((t) => el("th", { text: t })))),
        el("tbody", {}, ...sorted.flatMap((s) => itemRows(s, batched))))));
}

/* An item entry, and its description in the row under it (hidden while closed, but
   always in the page, so a quote in it is found and a draft on it stays anchored). */
function itemRows(s, batched) {
  const it = s.item;
  const open = openItems.has(s.id);
  const implementsCell = el("td", { class: "rv-implements" });
  [].concat(it.implements || []).forEach((name, k) => {
    if (k) implementsCell.append(", ");
    const i = lexiconIndex(name);
    implementsCell.append(i < 0 ? el("span", { text: name }) : el("span", { class: "term", "data-term": i, text: name }));
  });
  const entry = el("tr", { class: `rv-entry ${open ? "open" : ""}`, "data-item": s.id,
                           onclick: () => setItemOpen(s.id, !openItems.has(s.id)) },
    el("td", { class: "rv-item" },
      el("div", {},
        el("span", { class: "rv-chev", text: open ? "▾" : "▸" }),
        el("span", { class: "num", text: numberOf(s.id) }), " ",
        el("span", { class: "rv-title", text: s.title }),
        writingId() === s.id ? el("span", { class: "badge accent writing", text: "writing" }) : null,
        isUpdated(s.id) ? el("span", { class: "badge new", text: "updated" }) : null),
      el("div", { class: "rv-files" }, ...[].concat(it.files || []).map((f) => el("div", {}, fileRef(f))))),
    el("td", { class: "rv-verdict" }, verdictBadge(verdictOf(s))),
    batched ? el("td", { class: "rv-batch", text: hasBatch(s) ? String(s.item.batch) : "" }) : null,
    implementsCell,
    el("td", { class: "rv-note", text: it.note || "" }));
  const description = el("tr", { class: "rv-desc", id: `rv-desc-${s.id}`, hidden: !open },
    el("td", { colspan: batched ? "5" : "4" }, sectionBlock(s, { bare: true })));
  return [entry, description];
}

/* The structure view: a Mermaid flowchart drawn from the item fields. One frame per
   directory, one node per file outlined in the colour of its item's verdict, a file
   that is only the target of a relation greyed out (it is not in the diff). An arrow
   per relation, labelled with its kind, from the relation's `from` file if it names
   one, else from the first file of its item. A finding across items (a section with
   "kind": "finding" and "items": [item ids]) adds a dashed line from the first file of
   its first item to the first file of each other one, labelled with its number, and is
   listed under the chart as a section block, with the items it involves. Without
   relations or findings there is nothing to draw, and the view is left out. */
const filesOf = (s) => [].concat(s.item.files || []);
const relationsOf = (s) => [].concat(s.item.relations || []).filter((r) => r && r.to);

function structureView(items, findings) {
  if (!items.some((s) => relationsOf(s).length) && !findings.length) return null;
  const nodes = new Map(); // file path -> { id, cls }
  const node = (f, cls) => {
    if (!nodes.has(f)) nodes.set(f, { id: `f${nodes.size}`, cls });
    return nodes.get(f).id;
  };
  const vclass = (s) => `tc_${toneOf(verdictOf(s)) || "none"}`;
  items.forEach((s) => filesOf(s).forEach((f) => node(f, vclass(s))));
  const edges = [];
  for (const s of items) {
    for (const r of relationsOf(s)) {
      const from = r.from || filesOf(s)[0];
      if (!from) continue;
      edges.push(`${node(from, "vc_ghost")} -->${r.kind ? `|"${mq(r.kind)}"|` : ""} ${node(r.to, "vc_ghost")}`);
    }
  }
  const byId = new Map(items.map((s) => [s.id, s]));
  for (const f of findings) {
    const firsts = [].concat(f.items || []).map((id) => byId.get(id)).filter(Boolean)
      .map((s) => filesOf(s)[0]).filter(Boolean);
    for (const other of firsts.slice(1)) {
      if (other !== firsts[0]) edges.push(`${node(firsts[0])} -.-|"§${numberOf(f.id)}"| ${node(other)}`);
    }
  }
  const dirs = new Map(); // directory -> [file]
  for (const f of nodes.keys()) {
    const dir = f.includes("/") ? f.slice(0, f.lastIndexOf("/") + 1) : "./";
    dirs.set(dir, [...(dirs.get(dir) || []), f]);
  }
  const lines = ["flowchart LR"];
  [...dirs].forEach(([dir, files], i) => {
    lines.push(`  subgraph d${i}["${mq(dir)}"]`);
    for (const f of files) lines.push(`    ${nodes.get(f).id}["${mq(f.slice(f.lastIndexOf("/") + 1))}"]`);
    lines.push("  end");
  });
  lines.push(...edges.map((e) => `  ${e}`));
  for (const [, n] of nodes) lines.push(`  class ${n.id} ${n.cls}`);

  const involves = (f) => el("div", { class: "rv-involves dim" }, "involves: ",
    ...[].concat(f.items || []).flatMap((id, k) => [k ? ", " : null,
      byId.has(id) ? el("a", { href: `#sec-${id}`, text: titleOf(id),
                               onclick: (e) => { e.preventDefault(); scrollToSection(id); } })
                   : el("span", { text: id })]).filter(Boolean));
  return el("div", { class: "rv rv-wide rv-structure" },
    el("div", { class: "rv-head" }, "structure",
      el("span", { class: "rv-counts", text: "files by directory · arrows: relations · dashed: findings across items · greyed: not in the diff" })),
    el("pre", {}, el("code", { class: "language-mermaid", text: lines.join("\n") })),
    findings.length ? el("div", { class: "rv-head" }, "findings across items") : null,
    ...findings.map((f) => {
      const block = sectionBlock(f);
      block.classList.add("rv-finding");
      $("h2", block).after(involves(f));
      return block;
    }));
}
// Text inside a quoted Mermaid label: a double quote would end it.
const mq = (t) => String(t).replace(/"/g, "#quot;");

/* Open the item entry of section `id`, if it is an item drawn in the review table, so
   its description is on screen; returns the entry, else null. */
function openItemOf(id) {
  const entry = document.querySelector(`.rv-entry[data-item="${CSS.escape(id)}"]`);
  if (entry && !openItems.has(id)) setItemOpen(id, true);
  return entry;
}

function setItemOpen(id, open) {
  const entry = document.querySelector(`.rv-entry[data-item="${CSS.escape(id)}"]`);
  if (!entry) return;
  if (open) openItems.add(id); else openItems.delete(id);
  entry.classList.toggle("open", open);
  $(".rv-chev", entry).textContent = open ? "▾" : "▸";
  const description = document.getElementById(`rv-desc-${id}`);
  description.hidden = !open;
  if (open) renderMermaid(description);
  positionPopover();
  savePosition();
}

function typesetMath(root) {
  if (!window.katex) return;
  root.querySelectorAll(".math").forEach((m) => {
    if (m.dataset.tex === undefined) m.dataset.tex = m.textContent; // compared by the update diff
    try {
      katex.render(m.textContent, m, { displayMode: m.classList.contains("block"), throwOnError: false });
    } catch (e) { /* leave the TeX source visible */ }
  });
}

let mermaidLib = null;
/* Mermaid lays a chart out from the size of its text, which is zero in a hidden tab or
   a closed item entry: a chart out of sight stays a code block until it is shown (see
   setTab and setItemOpen, which call this again). */
async function renderMermaid(root) {
  const shown = (code) => code.isConnected && code.parentElement.getClientRects().length > 0;
  if (![...root.querySelectorAll("pre > code.language-mermaid")].some(shown)) return;
  try {
    mermaidLib = mermaidLib || (await import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")).default;
    const blocks = [...root.querySelectorAll("pre > code.language-mermaid")].filter(shown);
    if (!blocks.length) return;
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    mermaidLib.initialize({ startOnLoad: false, theme: dark ? "dark" : "default" });
    const nodes = blocks.map((code) => {
      const div = el("div", { class: "mermaid", "data-src": code.textContent, text: code.textContent });
      code.parentElement.replaceWith(div);
      return div;
    });
    await mermaidLib.run({ nodes });
    applyHighlights(); // the diagrams replaced their code blocks, and the ranges in them
  } catch (e) { /* offline: the source stays as a code block */ }
}

/* ---------------- code citations ---------------- */

/* In a code session, `path/to/file.py:42` (inline code) and [text](path/to/file.py:42)
   open the file at that line in VS Code. Paths are relative to the session's repo.
   Only known source extensions count, so `store.read_plan` or `v1.2` stay plain code. */
const EXTS = "py|pyi|js|mjs|ts|tsx|jsx|vue|svelte|md|json|jsonl|yaml|yml|toml|ini|cfg|sh|zsh|css|html|sql|rs|go|java|kt|swift|c|h|cpp|hpp|rb|lock|txt|env|ipynb";
const CITE_RE = new RegExp(`^((?:[\\w.@-]+/)*[\\w@-][\\w.@-]*\\.(?:${EXTS}))(?::(\\d+)(?:-\\d+)?)?$`);

function vscodeHref(target) {
  if (isTouch()) return null; // VS Code runs on the Mac, out of a phone's reach: plain code
  const m = CITE_RE.exec(target.trim());
  const repo = state.plan.repo;
  if (!m || !repo) return null;
  const abs = m[1].startsWith("/") ? m[1] : `${repo.replace(/\/$/, "")}/${m[1].replace(/^\.\//, "")}`;
  return `vscode://file${abs}${m[2] ? `:${m[2]}` : ""}`;
}

function linkCitations(root) {
  if (state.plan.kind !== "code") return;
  root.querySelectorAll("code").forEach((code) => {
    if (code.closest("pre, a")) return;
    const href = vscodeHref(code.textContent);
    if (!href) return;
    const a = el("a", { class: "cite", href, title: "Open in VS Code" });
    code.replaceWith(a);
    a.append(code);
  });
  root.querySelectorAll("a[href]").forEach((a) => {
    const raw = a.getAttribute("href");
    if (/^(https?:|vscode:|#|mailto:)/.test(raw)) return;
    const href = vscodeHref(decodeURIComponent(raw));
    if (href) { a.href = href; a.classList.add("cite"); a.title = "Open in VS Code"; }
  });
}

/* ---------------- term annotation ---------------- */

const SKIP = "code, pre, .katex, .mermaid, .term, .audit, h2";

function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

/* Wrap occurrences of `term` in text nodes under `root`. Word boundaries are
   letter-aware (é, ß count as letters) so "état" does not match inside "étatique". */
function wrapTerm(root, term, make, { first = false } = {}) {
  if (!term.trim()) return;
  const re = new RegExp(`(?<![\\p{L}\\p{N}])${escapeRe(term)}(?![\\p{L}\\p{N}])`, "iu");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (let node of nodes) {
    let m;
    while (node && (m = re.exec(node.data))) {
      const match = node.splitText(m.index);
      node = match.splitText(m[0].length);
      const span = make();
      match.replaceWith(span);
      span.append(match);
      if (first) return;
    }
  }
}

/* Entries on the same term in the same section (a term with several forward
   references) share one underline, whose tip lists every entry: a wrapped term is
   skipped by later wraps, so one wrap per term and section is all that renders. */
function annotateAudit(doc) {
  const groups = new Map();
  for (const a of state.audit || []) {
    const key = `${a.section || ""}\u0000${(a.term || "").toLowerCase()}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }
  for (const entries of groups.values()) {
    const { section, term } = entries[0];
    const sec = doc.querySelector(`#sec-${CSS.escape(section || "")} .body`);
    if (!sec) continue;
    const tip = entries.map((a) => `audit · ${a.issue || "flagged"}${a.note ? " — " + a.note : ""}`).join(" ; ");
    wrapTerm(sec, term || "", () => el("span", { class: "audit", "data-tip": tip }));
  }
}

/* Terms carry the index of their lexicon entry; the tooltip renders the entry's
   tip_html (the developed `tip`, else the one-line definition). */
function annotateLexicon(doc) {
  state.plan.lexicon.forEach((t, i) => {
    const home = doc.querySelector(`#sec-${CSS.escape(t.section || "")} .body`);
    if (home) wrapTerm(home, t.term, () => el("span", { class: "term def", "data-term": i }), { first: true });
    doc.querySelectorAll(".sec .body").forEach((body) =>
      wrapTerm(body, t.term, () => el("span", { class: "term", "data-term": i })));
  });
}

/* The texts of the agent questions under `root` (a question's text and background, its
   options) underline the lexicon terms too. A box is kept across renders: a term it
   already underlines is skipped, so annotating it again only adds new terms. */
function annotateQuestions(root) {
  const texts = root.querySelectorAll(".q-text, .q-options label > span:not(.badge)");
  state.plan.lexicon.forEach((t, i) => texts.forEach((n) =>
    wrapTerm(n, t.term, () => el("span", { class: "term", "data-term": i }))));
}

/* ---------------- section frames ----------------
   An HTML section is drawn in a section frame (frame.py): an <iframe> that loads the
   section's file from the server, sandboxed so it runs as a separate web page. Its block
   holds a slot where the frame goes. A frame is kept across re-renders while its file is
   unchanged (same version), so a figure does not reload whenever another file of the
   session changes: before a render the frames are parked, after it each one is moved
   into its section's slot. moveBefore keeps a moved frame running; a browser without it
   reloads the frame. The frame takes the height its content posts (static/frame.js).
   The page's tools reach a passage inside it through frame messages (static/frame.js):
   the frame posts the reader's selection, a click on a side thread's passage and the
   underlined term under the pointer; the page posts the passages to highlight (anchors),
   the one to reveal, the words added since the highlight baseline (changes) and the
   terms to underline (terms), which the frame paints over the words. */

// As frame.SANDBOX: scripts run, and no allow-same-origin, so the frame cannot reach the page.
const SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms";
const frames = new Map(); // section id -> its frame

function moveInto(parent, node, before = null) {
  if (parent.moveBefore && node.isConnected) parent.moveBefore(node, before);
  else parent.insertBefore(node, before);
}

function parkFrames() {
  const park = $("#frame-park");
  for (const f of frames.values()) if (f.isConnected && f.parentElement !== park) moveInto(park, f);
}

function placeFrames() {
  const placed = new Set();
  document.querySelectorAll(".frame-slot[data-frame]").forEach((slot) => {
    const id = slot.dataset.frame;
    if (placed.has(id)) return;
    const { version } = state.sections[id];
    let f = frames.get(id);
    if (!f || f.dataset.version !== version) {
      if (f) f.remove();
      f = el("iframe", { class: "frame", sandbox: SANDBOX, allow: "fullscreen", title: titleOf(id),
                         "data-version": version, src: `/s/${SLUG}/sections/${encodeURIComponent(id)}.html?v=${version}` });
      f.addEventListener("load", () => { postTheme(f); postAnchors(id, f); postChanges(id, f); postTerms(id, f); postHoles(id, f); });
      frames.set(id, f);
    }
    moveInto(slot, f);
    placed.add(id);
  });
  for (const [id, f] of frames) if (!placed.has(id)) { f.remove(); frames.delete(id); }
}

/* The theme tokens: the frame defines every theme; the page tells it which one it is in,
   at load and at every change of the page's theme. */
function postTheme(f) {
  if (f.contentWindow) f.contentWindow.postMessage({ viewConcept: "theme", theme: document.documentElement.dataset.theme }, "*");
}
new MutationObserver(() => frames.forEach(postTheme))
  .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

/* The frame messages a frame posts: its height, the reader's selection inside it, where
   a revealed passage sits, the side threads whose passage it found (placed), the side
   thread whose passage was clicked, and the term under the pointer (static/frame.js). */
const revealing = new Map(); // section id -> the comment whose passage its frame looks for

window.addEventListener("message", (e) => {
  const d = e.data;
  if (!d || typeof d.viewConcept !== "string") return;
  const hit = [...frames].find(([, f]) => f.contentWindow === e.source);
  if (!hit) return;
  const [id, f] = hit;
  if (d.viewConcept === "height") f.style.height = `${d.height}px`;
  else if (d.viewConcept === "selection") frameSelection(id, f, d);
  else if (d.viewConcept === "revealed") frameRevealed(id, f, d);
  else if (d.viewConcept === "placed") framePlaced(f, d);
  else if (d.viewConcept === "thread-click") frameThreadClick(id, f, d);
  else if (d.viewConcept === "hole-click") frameHoleClick(id, f, d);
  else if (d.viewConcept === "term-hover") frameTermHover(f, d);
  else if (d.viewConcept === "tap") tapElsewhere(f);
});

/* A rect of the frame's viewport, in the page's viewport. */
function pageRect(f, r) {
  const b = f.getBoundingClientRect();
  const x = b.left + f.clientLeft, y = b.top + f.clientTop;
  return { left: x + r.left, right: x + r.right, top: y + r.top, bottom: y + r.bottom,
           width: r.right - r.left, height: r.bottom - r.top };
}

/* The selection message: a passage selected in an HTML section gets the box a passage of
   a Markdown section gets, anchored the same way (section id, quote, prefix). */
function frameSelection(id, f, d) {
  if (!d.quote || !d.rect) {
    if (pendingSelection && pendingSelection.section === id) showSelection(null);
    return;
  }
  const rect = pageRect(f, d.rect);
  showSelection({ section: id, quote: collapse(String(d.quote)), prefix: collapse(String(d.prefix || "")), rect });
}

/* The anchors message: the passages the drafts, the sent comments and the side threads
   quote in an HTML section, which its frame highlights. */
const quotesIn = (id, list) => list.filter((c) => c.section === id && c.quote && !c.quote.startsWith("plan · "));
function postAnchors(id, f = frames.get(id)) {
  if (!f || !f.contentWindow || !state) return;
  const anchor = (kind) => ({ id: thread, quote, prefix }) =>
    ({ kind, quote, prefix: prefix || "", ...(kind === "thread" ? { thread } : {}) });
  const sent = state.comments.batches.flatMap((b) => b.comments).filter((c) => c.status === "sent");
  const anchors = [
    ...quotesIn(id, drafts).map(anchor("draft")),
    ...quotesIn(id, sent).map(anchor("sent")),
    ...quotesIn(id, threadsState.threads).map(anchor("thread")),
  ];
  f.contentWindow.postMessage({ viewConcept: "anchors", anchors }, "*");
}

/* The answer « placed » to the anchors: the side threads whose passage the frame found
   (f.placed), which get no chip in the section's heading, as a Markdown passage. */
function framePlaced(f, d) {
  if (!Array.isArray(d.threads)) return;
  f.placed = new Set(d.threads.map(String));
  if (state) renderThreadChips();
}

/* The thread click message: the reader clicked a passage the frame highlights for a side
   thread. Its thread opens on it, as on a passage of a Markdown section; the popover sits
   under the passage (frameThreads), and follows it when the view scrolls. */
const frameThreads = new Map(); // thread id -> { f, rect }: its passage, in its frame's viewport
function frameThreadClick(id, f, d) {
  const t = threadOf(String(d.thread));
  if (!t || t.section !== id || !d.rect) return;
  frameThreads.set(t.id, { f, rect: d.rect });
  openPopover(t.id);
}

/* The changes message: the words added to an HTML section since its highlight baseline.
   The page compares the visible text of the file now with the baseline file, word by
   word (the text frame.js indexes: the body's text outside its scripts and styles,
   whitespace collapsed, a space between two blocks), and posts each run of added words
   as a passage. The file is parsed, not run: its scripts do not run here. */
const HIDDEN_TAGS = "script, style, noscript, template";
// As frame.js: the elements whose text is not run on with the text around them.
const FRAME_BLOCKS = "address, article, aside, blockquote, dd, details, div, dl, dt, figcaption, figure, footer, " +
  "form, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, summary, table, td, th, tr, ul, " +
  "button, caption, label, option, text, tspan, br";
function visibleText(html) {
  const body = new DOMParser().parseFromString(html || "", "text/html").body;
  if (!body) return "";
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement.closest(HIDDEN_TAGS) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  let text = "", block = null;
  while (walker.nextNode()) {
    const n = walker.currentNode, b = n.parentElement.closest(FRAME_BLOCKS);
    if (b !== block) text += " ";
    block = b;
    text += n.data;
  }
  return collapse(text);
}
function addedPassages(sec) {
  if (!sec.updated) return [];
  const now = visibleText(sec.md);
  const spans = [];
  for (const m of now.matchAll(/\S+/g)) spans.push([m.index, m.index + m[0].length, m[0]]);
  const { inserted } = diffWords(visibleText(sec.seen).split(" ").filter(Boolean), spans.map((w) => w[2]));
  const out = [];
  let run = null;
  spans.forEach(([a, b], k) => {
    if (!inserted.has(k)) { run = null; return; }
    if (run) run.end = b;
    else out.push(run = { start: a, end: b });
  });
  return out.map(({ start, end }) => ({ quote: now.slice(start, end), prefix: now.slice(Math.max(0, start - 32), start) }));
}
function postChanges(id, f = frames.get(id)) {
  const sec = state && state.sections[id];
  if (!f || !f.contentWindow || !sec) return;
  f.contentWindow.postMessage({ viewConcept: "changes", changes: addedPassages(sec) }, "*");
}

/* The terms message: what the page underlines in a Markdown section, for the frame to
   paint over the words: the audit's entries on this section (one per term, their notes
   joined, as annotateAudit does), the term this section is the home of, and every
   lexicon term. Each carries the key its term hover message gives back. */
function postTerms(id, f = frames.get(id)) {
  if (!f || !f.contentWindow || !state) return;
  const audit = new Map();
  for (const a of state.audit || []) {
    if ((a.section || "") !== id || !a.term) continue;
    const k = a.term.toLowerCase();
    if (!audit.has(k)) audit.set(k, { term: a.term, notes: [] });
    audit.get(k).notes.push(`audit · ${a.issue || "flagged"}${a.note ? " — " + a.note : ""}`);
  }
  const terms = [...audit.values()].map((a) => ({ term: a.term, kind: "audit", key: { tip: a.notes.join(" ; ") } }));
  state.plan.lexicon.forEach((t, i) => {
    if (t.section === id) terms.push({ term: t.term, kind: "def", key: { term: i } });
    terms.push({ term: t.term, kind: "term", key: { term: i } });
  });
  f.contentWindow.postMessage({ viewConcept: "terms", terms }, "*");
}

/* The term hover message: the tip of the term under the pointer, under the word, as over
   a Markdown section; nothing once the pointer leaves it. */
function frameTermHover(f, d) {
  const key = d.key || {};
  if (!d.rect || (!Number.isInteger(key.term) && typeof key.tip !== "string")) { $("#tip").hidden = true; return; }
  if (Number.isInteger(key.term) && !state.plan.lexicon[key.term]) return;
  showTip(key.tip ?? null, key.term ?? null, pageRect(f, d.rect));
}

/* The reveal message: the frame finds the passage and answers where it sits; the frame
   takes the height of its content, so the page does the scrolling. */
function frameRevealed(id, f, d) {
  const asked = revealing.get(id);
  if (!revealing.delete(id)) return;
  // A line of the hole index: the boxes open on the element, or on the line without one.
  if (asked.holes) {
    openHolePop(id, asked.holes, d.found
      ? { f, rect: { left: d.left ?? 0, right: d.right ?? 0, top: d.top, bottom: d.bottom } } : { line: asked.holes[0] });
  }
  if (!d.found) { scrollToSection(id); return; }
  const r = pageRect(f, { left: 0, right: 0, top: d.top, bottom: d.bottom });
  const view = f.closest(".view");
  if (!view) return;
  const v = view.getBoundingClientRect();
  releaseAnchor();
  pageScroll(view, () => view.scrollBy({ top: (r.top + r.bottom) / 2 - (v.top + view.clientHeight / 2), behavior: "smooth" }));
}

/* ---------------- quotes <-> ranges ---------------- */

/* Text of a section body with whitespace collapsed, plus the DOM position of every
   character, so a quote taken from a selection can be found again after a re-render. */
function textIndex(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let text = "";
  const pos = [];
  let space = true;
  while (walker.nextNode()) {
    const n = walker.currentNode;
    for (let i = 0; i < n.data.length; i++) {
      const ws = /\s/.test(n.data[i]);
      if (ws && space) continue;
      text += ws ? " " : n.data[i];
      pos.push([n, i]);
      space = ws;
    }
  }
  return { text, pos };
}

/* The range of a quote in section `sectionId`. A quote on a missing fact (`fact`, its id)
   is looked for in that fact; one not found in a doc's text, in the doc's missing facts;
   one on a row of a Doc tab table (`rowOf`), in that row. */
function findQuote(sectionId, quote, prefix, fact = "") {
  const sec = `#sec-${CSS.escape(sectionId)}`;
  if (rowOf(sectionId)) return findIn(document.querySelector(`[data-anchor="${CSS.escape(sectionId)}"]`), quote, "");
  if (fact) return findIn(document.querySelector(`${sec} .doc-facts [data-fact="${CSS.escape(fact)}"]`), quote, "");
  return findIn(document.querySelector(`${sec} .body`), quote, prefix)
    || findIn(document.querySelector(`${sec} .doc-facts`), quote, prefix);
}

function findIn(body, quote, prefix) {
  if (!body || !quote) return null;
  const { text, pos } = textIndex(body);
  const q = collapse(quote);
  let at = prefix ? text.indexOf(collapse(prefix) + q) : -1;
  at = at >= 0 ? at + collapse(prefix).length : text.indexOf(q);
  if (at < 0) return null;
  const [sn, so] = pos[at];
  const [en, eo] = pos[at + q.length - 1];
  const r = document.createRange();
  r.setStart(sn, so);
  r.setEnd(en, eo + 1);
  return r;
}

function applyHighlights() {
  threadRanges = threadsState.threads.filter((t) => t.quote)
    .map((t) => [t, findQuote(t.section, t.quote, t.prefix, t.fact)]).filter(([, r]) => r);
  staleRanges = docsOf().stale.filter((s) => s.doc === shownDoc).map((s) => [s, findStale(s)]).filter(([, r]) => r);
  if (!window.CSS || !CSS.highlights) return;
  CSS.highlights.set("ev-stale", new Highlight(...staleRanges.map(([, r]) => r)));
  const draftRanges = drafts.map((d) => findQuote(d.section, d.quote, d.prefix, d.fact)).filter(Boolean);
  const sentRanges = state.comments.batches.flatMap((b) => b.comments)
    .filter((c) => c.status === "sent")
    .map((c) => findQuote(c.section, c.quote, c.prefix, c.fact)).filter(Boolean);
  CSS.highlights.set("ev-draft", new Highlight(...draftRanges));
  CSS.highlights.set("ev-sent", new Highlight(...sentRanges));
  CSS.highlights.set("ev-thread", new Highlight(...threadRanges.map(([, r]) => r)));
  frames.forEach((f, id) => postAnchors(id, f));
  markUpdates();
}

/* ---------------- updates since the last batch ----------------
   An updated section carries the HTML of its highlight baseline: its text when the last
   batch was sent, or when the user last marked it read.
   Both versions are cut into words, the words are diffed, and every block (paragraph,
   list item, cell…) holding an insertion or a deletion gets a bar in the margin, always
   drawn. The words the rewrite inserted show ("ev-updated") only while the pointer is
   over their block; a block marked only for deleted words shows nothing on hover.
   « updated · mark read » in the section heading marks the section as read. A doc of the
   Doc tab is compared the same way (its view in `state.docs`, the key "doc:<path>"), and
   gets the base mark too (markBase). */

const BLOCKS = "p, li, td, th, pre, blockquote, h1, h2, h3, h4, h5, h6, dt, dd, .math.block, .mermaid";

// The source of a formula or a diagram, which counts as one word; null for any other element.
const atomOf = (n) => n.matches(".math") ? n.dataset.tex ?? n.textContent
                    : n.matches(".mermaid") ? n.dataset.src
                    : n.matches("pre > code.language-mermaid") ? n.textContent : null;

/* The words of `root`, each with the DOM range it covers. A formula or a diagram is one
   word (its source), so a re-typeset formula compares equal to its TeX. The same
   function reads the detached read version and the live, annotated section. */
function words(root) {
  const out = [];
  let cur = null;
  const end = () => { if (cur) out.push(cur); cur = null; };
  const blockOf = (n) => (n.nodeType === 1 ? n : n.parentElement).closest(BLOCKS) || root;
  const walk = (node) => {
    for (const n of node.childNodes) {
      if (n.nodeType === 1) {
        const atom = atomOf(n);
        if (atom != null) {
          end();
          const range = document.createRange();
          range.selectNode(n);
          out.push({ text: `\u0000${collapse(atom)}`, range, block: blockOf(n) });
        } else walk(n);
      } else if (n.nodeType === 3) {
        const block = blockOf(n);
        if (cur && cur.block !== block) end();
        for (let i = 0; i < n.data.length; i++) {
          if (/\s/.test(n.data[i])) { end(); continue; }
          if (!cur) {
            cur = { text: "", range: document.createRange(), block };
            cur.range.setStart(n, i);
          }
          cur.text += n.data[i];
          cur.range.setEnd(n, i + 1);
        }
      }
    }
  };
  walk(root);
  end();
  return out;
}

/* Which words of `b` are not in `a` (`inserted`), which words of `b` follow a run of
   words of `a` that is gone (`deleted`), and for each word of `a` the index of its pair
   in `b`, -1 when it has none (`pairs`). Longest common subsequence, after trimming the
   common head and tail; a middle too large to compare counts as rewritten. */
function diffWords(a, b) {
  let lo = 0;
  while (lo < a.length && lo < b.length && a[lo] === b[lo]) lo++;
  let ea = a.length, eb = b.length;
  while (ea > lo && eb > lo && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const n = ea - lo, m = eb - lo;
  const inserted = new Set(), deleted = new Set();
  const pairs = new Int32Array(a.length).fill(-1);
  for (let k = 0; k < lo; k++) pairs[k] = k;
  for (let k = ea; k < a.length; k++) pairs[k] = k - ea + eb;
  if (n * m > 4e6) {
    for (let j = lo; j < eb; j++) inserted.add(j);
    if (n) deleted.add(Math.min(lo, b.length - 1));
    return { inserted, deleted, pairs };
  }
  const L = new Int32Array((n + 1) * (m + 1)); // L[i][j]: LCS of a[lo+i..ea) and b[lo+j..eb)
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      L[i * (m + 1) + j] = a[lo + i] === b[lo + j] ? L[(i + 1) * (m + 1) + j + 1] + 1
        : Math.max(L[(i + 1) * (m + 1) + j], L[i * (m + 1) + j + 1]);
    }
  }
  let i = 0, j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[lo + i] === b[lo + j]) { pairs[lo + i] = lo + j; i++; j++; }
    else if (j < m && (i === n || L[i * (m + 1) + j + 1] >= L[(i + 1) * (m + 1) + j])) inserted.add(lo + j++);
    else { deleted.add(Math.min(lo + j, b.length - 1)); i++; }
  }
  return { inserted, deleted, pairs };
}

/* The ranges of inserted words of each .changed block, and the block the pointer is over:
   only its ranges are painted (a ::highlight cannot be scoped to :hover). */
let changeRanges = new Map();
let hoveredChange = null;

function paintChange(block) {
  hoveredChange = block;
  if (window.CSS && CSS.highlights) CSS.highlights.set("ev-updated", new Highlight(...(changeRanges.get(block) || [])));
}

// The .changed block of a Markdown section that holds `node`, or null.
const changedBlock = (node) => {
  const b = node && node.closest ? node.closest(".sec .body .changed") : null;
  return b && changeRanges.has(b) ? b : null;
};

for (const view of docViews()) {
  view.addEventListener("mouseover", (e) => {
    if (isTouch()) return; // a tap paints it (see "taps")
    const b = changedBlock(e.target);
    if (b !== hoveredChange) paintChange(b);
  });
  view.addEventListener("mouseleave", () => { if (hoveredChange && !isTouch()) paintChange(null); });
}

function markUpdates() {
  document.querySelectorAll(".changed").forEach((n) => n.classList.remove("changed"));
  changeRanges = new Map();
  const docs = docsOf();
  const entries = [...Object.entries(state.sections),
                   ...Object.entries(docs.views).filter(([path, v]) => v.exists && !(docEdit && docEdit.path === path))
                     .map(([path, v]) => [DOC_PREFIX + path, v])];
  for (const [id, sec] of entries) {
    const body = sec.updated && document.querySelector(`#sec-${CSS.escape(id)} .body`);
    if (!body) continue;
    // A section frame is out of the page's reach: its rectangle gets the change bar (it also
    // marks words only removed), and the changes message has the frame highlight the words added.
    if (sec.kind === "html") { body.querySelectorAll(".frame-slot").forEach((n) => n.classList.add("changed")); continue; }
    const before = document.createElement("div");
    before.innerHTML = sec.seen_html || "";
    const now = words(body);
    const { inserted, deleted } = diffWords(words(before).map((w) => w.text), now.map((w) => w.text));
    for (const k of deleted) if (now[k]) now[k].block.classList.add("changed");
    // One range per run of inserted words in a block, so the spaces between them are highlighted too.
    let run = null;
    now.forEach((w, k) => {
      if (!inserted.has(k)) { run = null; return; }
      w.block.classList.add("changed");
      if (run && run.block === w.block) run.range.setEnd(w.range.endContainer, w.range.endOffset);
      else {
        run = { block: w.block, range: w.range.cloneRange() };
        if (!changeRanges.has(w.block)) changeRanges.set(w.block, []);
        changeRanges.get(w.block).push(run.range);
      }
    });
  }
  // The blocks were redrawn: paint the one under the pointer now, if any (a tap's paint
  // goes with the block it was on).
  const under = isTouch() ? null : [...document.querySelectorAll(":hover")].pop();
  paintChange(changedBlock(under));
  frames.forEach((f, id) => postChanges(id, f));
  markBase();
}

/* The base mark of the doc shown: each block (its own words, as the change highlights cut
   them) whose text is not the text of a block of the doc at the merge base gets the bar;
   every block of a doc created on the branch. In a doc that existed at the base, the words
   of a barred block that the base did not have are painted too ("ev-base"), always, under
   every other highlight (a lower priority): the green words of a rewrite show over them.
   A block moved whole keeps its text, so it gets neither. No base (`base_html` null and not
   `new`): no mark. */
function markBase() {
  document.querySelectorAll(".based").forEach((n) => n.classList.remove("based"));
  const paint = (ranges) => {
    if (!window.CSS || !CSS.highlights) return;
    const h = new Highlight(...ranges);
    h.priority = -1;
    CSS.highlights.set("ev-base", h);
  };
  paint([]);
  const v = shownDoc && docsOf().views[shownDoc];
  if (!v || !v.exists || (!v.new && v.base_html == null) || (docEdit && docEdit.path === shownDoc)) return;
  const body = document.querySelector(`#sec-${CSS.escape(DOC_PREFIX + shownDoc)} .body`);
  if (!body) return;
  const blockTexts = (root) => {
    const m = new Map();
    for (const w of words(root)) if (w.block !== root) m.set(w.block, `${m.has(w.block) ? `${m.get(w.block)} ` : ""}${w.text}`);
    return m;
  };
  let base = new Set();
  const before = document.createElement("div");
  if (!v.new) {
    before.innerHTML = v.base_html;
    base = new Set(blockTexts(before).values());
  }
  for (const [block, text] of blockTexts(body)) if (v.new || !base.has(text)) block.classList.add("based");
  if (v.new) return;
  // One range per run of words added since the base in a barred block, as in markUpdates.
  const now = words(body);
  const { inserted } = diffWords(words(before).map((w) => w.text), now.map((w) => w.text));
  const ranges = [];
  let run = null;
  now.forEach((w, k) => {
    if (!inserted.has(k) || !w.block.classList.contains("based")) { run = null; return; }
    if (run && run.block === w.block) run.range.setEnd(w.range.endContainer, w.range.endOffset);
    else {
      run = { block: w.block, range: w.range.cloneRange() };
      ranges.push(run.range);
    }
  });
  paint(ranges);
}

// The text a « mark read » records: a section's file, or a doc's (key "doc:<path>").
const mdOf = (id) => (docPathOf(id) !== null ? (docsOf().views[docPathOf(id)] || {}).md || "" : state.sections[id].md);

// A doc's « mark read » marks its missing facts read too (key "facts:<path>").
const FACTS_PREFIX = "facts:";
async function markSeen(ids) {
  const read = ids.map((id) => [id, mdOf(id)]);
  for (const id of ids) {
    const facts = (docsOf().facts || {})[docPathOf(id)];
    if (facts) read.push([FACTS_PREFIX + docPathOf(id), facts.text]);
  }
  await markRead(Object.fromEntries(read));
}

// Move highlight baselines: {key: text}.
async function markRead(sections) {
  try {
    await postJSON(`/api/s/${SLUG}/seen`, { sections });
  } catch (e) { toast(`Could not mark as read: ${e.message}`); return; }
  await load();
}

function revealQuote(c) {
  if (!c.section) return;
  if (c.quote.startsWith("plan · ")) { setTab("plan"); return; }
  openSection(c.section);
  openItemOf(c.section);
  const f = c.quote && (state.sections[c.section] || {}).kind === "html" && frames.get(c.section);
  if (f && f.contentWindow) {
    revealing.set(c.section, c);
    f.contentWindow.postMessage({ viewConcept: "reveal", quote: c.quote, prefix: c.prefix || "" }, "*");
    return;
  }
  const r = findQuote(c.section, c.quote, c.prefix, c.fact);
  if (r) {
    const p = r.startContainer.parentElement;
    pageScroll(p.closest(".view"), () => p.scrollIntoView({ block: "center", behavior: "smooth" }));
    if (CSS.highlights) {
      CSS.highlights.set("ev-focus", new Highlight(r));
      setTimeout(() => CSS.highlights.delete("ev-focus"), 1500);
    }
  } else scrollToSection(c.section);
}

/* A section that is an item is reached through its item entry: the entry opens, and is
   what scrolls into view, with its description under it. */
function scrollToSection(id) {
  openSection(id);
  const s = openItemOf(id) || document.getElementById(`sec-${id}`);
  if (s) pageScroll(s.closest(".view"), () => s.scrollIntoView({ block: "start", behavior: "smooth" }));
}

/* ---------------- selection -> composer ---------------- */

function currentSelection() {
  const sel = getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
  const sec = start.closest(".sec");
  if (!sec || !sec.closest("#model, #refactor, #doc")) return null;
  const body = $(".body", sec);
  const quote = collapse(sel.toString());
  if (!quote) return null;
  // A passage of a row of a Doc tab table: anchored to the row.
  const row = start.closest("[data-anchor]");
  if (row) return { section: row.dataset.anchor, quote, prefix: "", rect: range.getBoundingClientRect() };
  if (!sec.dataset.id) return null; // a table's heading: only its rows are commented
  // A passage of a missing fact: anchored to the doc, carrying the fact's id.
  const fact = start.closest("[data-fact]");
  if (fact) return { section: sec.dataset.id, quote, prefix: "", fact: fact.dataset.fact, rect: range.getBoundingClientRect() };
  const before = document.createRange();
  before.setStart(body, 0);
  before.setEnd(range.startContainer, range.startOffset);
  const prefix = collapse(before.toString()).slice(-32);
  return { section: sec.dataset.id, quote, prefix, rect: range.getBoundingClientRect() };
}

/* The page reads the selection each time it changes: a finger releases no mouse button
   (the phone selects a word on a long press, then grows the selection as its handles are
   dragged). With a mouse, « + comment » and « ask » show just under the selection; under
   touch controls they sit in the selection bar, fixed at the bottom of the screen
   (app.css), out of reach of the phone's own menu and handles. Clearing the selection
   hides them. A button takes the selection as it stood before the tap, even when the
   phone clears it on the tap. A section frame posts its selection the same way
   (frameSelection). */
let barPressed = 0; // when a finger last went down on the selection bar

function showSelection(s) {
  const btn = $("#sel-actions");
  if (!s) {
    // The phone may clear the selection as the bar is tapped: the tap still takes it.
    if (Date.now() - barPressed < 800) return;
    btn.hidden = true;
    pendingSelection = null;
    return;
  }
  pendingSelection = s;
  btn.hidden = false;
  btn.style.top = `${window.scrollY + s.rect.bottom + 6}px`;
  btn.style.left = `${Math.max(8, s.rect.left)}px`;
}

let selectionTimer = null;
document.addEventListener("selectionchange", () => {
  if (document.activeElement && document.activeElement.closest("textarea, input")) return;
  clearTimeout(selectionTimer);
  selectionTimer = setTimeout(() => {
    const s = currentSelection();
    // A frame's selection lives in the frame: the page's own empty one does not clear it.
    if (s || !pendingSelection || !frames.has(pendingSelection.section)) showSelection(s);
  }, 0);
});

document.addEventListener("mouseup", (e) => {
  if (isTouch() || e.target.closest("#composer, #sel-actions, #thread-pop, .doc-editor")) return;
  setTimeout(() => {
    const s = currentSelection();
    showSelection(s);
    if (!s) {
      const t = threadAt(e.clientX, e.clientY);
      if (t) openPopover(t.id);
    }
  }, 0);
});

$("#sel-actions").addEventListener("mousedown", (e) => e.preventDefault());
$("#sel-actions").addEventListener("pointerdown", () => { barPressed = Date.now(); });
$("#sel-actions .comment").addEventListener("click", () => {
  if (pendingSelection) openComposer(pendingSelection);
});
$("#sel-actions .ask").addEventListener("click", () => {
  if (pendingSelection) openComposer(pendingSelection, "ask");
});

/* ---------------- taps ----------------
   Under touch controls a tap does what a resting pointer does with a mouse: on an
   underlined term, its tip (a tap elsewhere or a scroll hides it); on a changed block,
   its new words, until a tap elsewhere; on a side thread's passage, the thread. A term
   inside a thread's passage shows its tip; the rest of the passage opens the thread.
   A tap anywhere else in the page, or in a section frame, clears the paint (the frame
   posts its taps: the tap message), and a scroll of any pane hides the tip. */
document.addEventListener("click", (e) => {
  if (!isTouch() || e.target.closest("#composer, #sel-actions, #thread-pop, #tip")) return;
  const sel = getSelection();
  if (sel.rangeCount && !sel.isCollapsed) return;
  const t = e.target.closest && e.target.closest("[data-tip], [data-term]");
  const stale = !t && staleAt(e.clientX, e.clientY);
  if (t) showTip(t.dataset.tip, t.dataset.term !== undefined ? Number(t.dataset.term) : null, t.getBoundingClientRect(), lexiconOf(t));
  else if (stale) showTip(staleNote(stale[0]), null, stale[1]);
  else $("#tip").hidden = true;
  const b = changedBlock(e.target);
  if (b !== hoveredChange) paintChange(b);
  tapElsewhere(null);
  if (!t && e.target.closest(".view")) {
    const th = threadAt(e.clientX, e.clientY);
    if (th) openPopover(th.id);
  }
});
// A tap outside the section frame `tapped` (null: on the page itself): the other frames
// clear their paint, and so does the page when the tap was in a frame.
function tapElsewhere(tapped) {
  if (tapped && hoveredChange) paintChange(null);
  frames.forEach((f) => { if (f !== tapped && f.contentWindow) f.contentWindow.postMessage({ viewConcept: "tap-elsewhere" }, "*"); });
}
// Scroll events do not bubble: listen in the capture phase to hear every pane's.
document.addEventListener("scroll", (e) => {
  if (isTouch() && !(e.target.closest && e.target.closest("#tip"))) $("#tip").hidden = true;
}, { capture: true, passive: true });

/* The composer writes either a draft comment ("comment") or the first message of a
   new side thread ("ask"). */
function openComposer(target, mode = "comment") {
  $("#sel-actions").hidden = true;
  const c = $("#composer");
  c.hidden = false;
  c._target = target;
  c._mode = mode;
  $(".composer-quote", c).textContent = target.question ? `agent question ${target.question}`
    : target.fact ? `missing fact ${target.fact} « ${target.quote.length > 160 ? target.quote.slice(0, 160) + "…" : target.quote} »`
    : rowOf(target.section) ? `${rowLabel(target.section)} « ${target.quote.length > 160 ? target.quote.slice(0, 160) + "…" : target.quote} »`
    : target.quote ? `« ${target.quote.length > 160 ? target.quote.slice(0, 160) + "…" : target.quote} »`
    : target.section === DOC_SET ? "the doc set"
    : docPathOf(target.section) !== null ? `whole doc ${docPathOf(target.section)}`
    : target.section ? `whole section §${numberOf(target.section)} ${titleOf(target.section)}`
    : "general question, no passage";
  $(".add", c).textContent = mode === "ask" ? "Ask" : "Add";
  $("#no-parent").hidden = mode !== "ask" || threadsState.forkable;
  // Under touch controls the hints name no shortcut: a phone keyboard has no ⌘.
  $("textarea", c).placeholder = mode === "ask"
    ? (isTouch() ? "Your question for a side thread" : "Your question for a side thread  (↵ to ask, ⇧↵ for a new line, Esc to cancel)")
    : (isTouch() ? "Your comment" : "Your comment  (⌘↵ to add, Esc to cancel)");
  const rect = target.rect || document.getElementById(`sec-${target.section}`).getBoundingClientRect();
  c.style.top = `${window.scrollY + Math.min(rect.bottom + 6, innerHeight - 220)}px`;
  c.style.left = `${Math.min(Math.max(8, rect.left), innerWidth - 380)}px`;
  const ta = $("textarea", c);
  ta.value = "";
  ta.focus();
}

function closeComposer() { $("#composer").hidden = true; }

/* The keyboard's height, as --keyboard: in the narrow layout the composer and a side
   thread dock across the bottom of the screen, above it. A phone browser that does not
   shrink the page for its keyboard still shrinks the visual viewport. */
function trackKeyboard() {
  const vv = window.visualViewport;
  if (!vv) return;
  const update = () => {
    const covered = Math.max(0, innerHeight - (vv.height + vv.offsetTop));
    document.documentElement.style.setProperty("--keyboard", `${Math.round(covered)}px`);
  };
  vv.addEventListener("resize", update);
  vv.addEventListener("scroll", update);
  update();
}
trackKeyboard();

function submitComposer() {
  if ($("#composer")._mode === "ask") askThread();
  else addDraft();
}

function addDraft() {
  const c = $("#composer");
  const text = $("textarea", c).value.trim();
  if (!text) return;
  const { section, quote, prefix, fact } = c._target;
  const d = { id: crypto.randomUUID(), section, quote, prefix, text, ...(fact ? { fact } : {}) };
  drafts.push(d);
  saveDraft(d);
  closeComposer();
  getSelection().removeAllRanges();
  renderReview();
  applyHighlights();
}

$("#composer .add").addEventListener("click", submitComposer);
$("#composer .cancel").addEventListener("click", closeComposer);
// In a thread, Enter sends and Shift+Enter breaks the line; a comment keeps ⌘↵. Under
// touch controls Enter breaks the line (a phone keyboard's only way to) and the button sends.
const sendsOnEnter = (e) => !isTouch() && e.key === "Enter" && !e.shiftKey && !e.isComposing;

$("#composer textarea").addEventListener("keydown", (e) => {
  const ask = $("#composer")._mode === "ask";
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey || (ask && sendsOnEnter(e)))) { e.preventDefault(); submitComposer(); }
  if (e.key === "Escape") closeComposer();
});

/* ---------------- agent questions: the scope block ----------------
   An agent question is one the agent puts to the user in the page (`view-concept question`,
   questions.json): its text, optional options (one choice, or several when `multi`),
   always a free-text field, and maybe a recommended answer (`recommended`). Every agent
   question lives in the scope block, at the top of the Plan tab: one box per open
   question, oldest first, then the answered and skipped ones folded under « answered ».
   The review pane only counts the open ones (see renderWaiting).
   A box is built once and kept while its question is open, so a re-render never takes
   the user's choice or text. A recommended answer that is one of the options is
   preselected; any other is pre-filled in the text field; either is marked « suggested ».
   A question may carry a background (the mechanism as it is today, each option's
   trade-offs), shown folded under its text. A hole (a question anchored on a scoping
   section) may name the element of the drawing it bears on (`element`): the frame marks
   it (postHoles), a click on it opens the box there (see "the hole popover"), and a chip
   in the box's text reveals it; a supposition (`kind:
   "supposition"`) is a hole the agent already answered, its one option « approve »
   preselected, the text field for a correction. A question with an anchor section (`section`)
   whose section is written is shown at the end of that section in the Model tab instead,
   and the scope block keeps a line pointing to it (see sectionQuestions).
   « ask » opens a side thread on the question, to understand it before answering; the
   box shows its threads as chips, and the answer, whichever exit, names them (see
   "side threads" for « use as answer », which fills the box from a thread).
   A box has four exits: « Validate » sends the answer at once (a batch whose action is
   "answer"), « Skip » sends « no answer, use your default » the same way (its entry
   `{question, skipped: true}`), « I don't understand » sends the text field as a note of
   what is missing (its entry `{question, unclear: true, note}`: the options are ignored,
   and the question is deferred until the agent asks it again, after the section that
   explains it), or the box stays open: no question blocks the agent, except during the
   pause of a feature's writer, which « Go on » ends (see paused).
   The header holds « Grill me » (a batch whose action is "grill"; « Stop grill » sends
   "stop-grill" while a grill runs) and, while scoping runs or a question is open,
   « Write plan » (action "plan": scoping ends, the open questions count as skipped, but a
   section question whose section is not written yet, which stays open; once a
   plan exists it reads « Rewrite plan », and the agent revises the plan with the answers).
   In a feature or a triage, what is written is the model: « Write model ».
   These three take the draft comments with them, like the approvals.
   A docs review (review-docs) has no Plan tab: its scope block, headed « questions », sits at
   the top of the Doc tab while it holds a question, without these three buttons. */

const openQuestions = () => (state ? state.questions || [] : []).filter((q) => q.status === "open");
// An open question shown at the end of its anchor section, once that section is written.
const atSection = (q) => !!q.section && q.section in state.sections;
const sectionQuestions = (id) => openQuestions().filter((q) => q.section === id && atSection(q));
const questionCards = new Map(); // question id -> its box

function questionCard(q) {
  if (questionCards.has(q.id)) return questionCards.get(q.id);
  const type = q.multi ? "checkbox" : "radio";
  const rec = q.recommended || "";
  const recOption = q.options.includes(rec);
  const suggested = () => el("span", { class: "badge accent", text: "suggested" });
  const options = el("div", { class: "q-options" }, ...q.options.map((o) =>
    el("label", {}, el("input", { type, name: `answer-${q.id}`, value: o, checked: recOption && o === rec }),
       el("span", { text: o }), recOption && o === rec ? suggested() : null)));
  const ta = el("textarea", { class: "c-text", rows: "2",
                              placeholder: q.options.length ? "Something to add, or another answer (optional)" : "Your answer" });
  if (rec && !recOption) ta.value = rec;
  const skip = el("button", { class: "btn", text: "Skip", title: "No answer: the agent uses its default" });
  const unclear = el("button", { class: "btn", text: "I don't understand",
                                 title: "The model explains what this question needs, then asks it again. The text field, if filled, says what is missing; the options are ignored" });
  const button = el("button", { class: "btn primary q-answer", text: "Validate" });
  const ask = el("button", { class: "btn q-ask", text: "ask", title: "Open a side thread to discuss this question before answering it",
                             onclick: (e) => openComposer({ section: q.section || "", quote: "", prefix: "", question: q.id,
                                                            rect: e.currentTarget.getBoundingClientRect() }, "ask") });
  const choices = () => [...options.querySelectorAll("input:checked")].map((i) => i.value);
  const update = () => { button.disabled = !choices().length && !ta.value.trim(); };
  update();
  options.addEventListener("change", update);
  ta.addEventListener("input", update);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); button.click(); }
  });
  const exit = async (path, body, done) => {
    button.disabled = skip.disabled = unclear.disabled = true;
    try {
      await postJSON(`/api/s/${SLUG}/questions/${q.id}/${path}`, body);
    } catch (e) { toast(`${done} failed: ${e.message}`); skip.disabled = unclear.disabled = false; update(); return; }
    await load();
    sentToast(`${done} ${q.id}`);
  };
  button.addEventListener("click", () => { if (!button.disabled) exit("answer", { choices: choices(), text: ta.value }, "Answered"); });
  skip.addEventListener("click", () => { if (!skip.disabled) exit("skip", {}, "Skipped"); });
  unclear.addEventListener("click", () => { if (!unclear.disabled) exit("unclear", { note: ta.value }, "Deferred"); });
  // A hole of the drawing names the element it bears on: its chip shows it there.
  const element = q.element ? el("button", { class: "badge accent q-element", text: q.element,
                                             title: "Show this element in the drawing",
                                             onclick: () => revealElement(q.section, q.element) }) : null;
  const supposition = q.kind === "supposition"
    ? el("span", { class: "badge tone-info", text: "supposition", title: "The agent's answer: approve it, or correct it in the text" }) : null;
  const card = el("div", { class: "question", "data-question": q.id },
    el("div", { class: "q-text" }, el("span", { class: "num", text: q.id }), " ", supposition, supposition ? " " : null,
       element, element ? " " : null, q.text),
    q.background ? el("details", { class: "q-background" }, el("summary", { text: "background" }),
                      el("div", { class: "q-text", text: q.background })) : null,
    q.options.length ? options : null,
    rec && !recOption ? el("div", { class: "q-suggested" }, suggested()) : null,
    ta,
    el("div", { class: "q-actions" }, el("span", { class: "t-chips", "data-question": q.id }), ask, unclear, skip, button));
  // « use as answer » puts a thread's draft in the box (see applyDraft).
  card._fill = ({ choices: picked, text }) => {
    for (const i of options.querySelectorAll("input")) i.checked = picked.includes(i.value);
    ta.value = text;
    update();
  };
  questionCards.set(q.id, card);
  return card;
}

/* A pause: in a feature, the writer stops after a section that opened questions while
   sections of the modeling part are left to write, and the coordinator sets the phase
   awaiting-answer. The page reads the pause from that phase, not from the open questions: a
   question left open by an earlier « Go on » still sits at the end of a written section
   while the writer writes on. « Go on » ends the pause without answering: a batch whose
   action is "go-on", after which the writer writes the next sections and the pause's
   questions stay open; the writer's next status ends the phase, and the button with it.
   It shows under the paused section's boxes and in the scope block, in place of
   « Rewrite model » (which would skip those questions and start a rewrite). Once every
   section is written there is no pause: a question still open holds back « Approve model »,
   as any open question does. */
function paused() {
  if (state.workflow !== "build-feature" || state.status.phase !== "awaiting-answer" || goOnPending()) return false;
  return (state.plan.outline || []).some((s) => !isRefactorSection(s) && !(s.id in state.sections));
}

// A « go-on » batch sent since the status last moved: the writer is going on.
function goOnPending() {
  const since = state.status.since || "";
  return state.comments.batches.some((b) => b.action === "go-on" && b.sent >= since);
}

const goOnButton = () => el("button", {
  class: "btn primary go-on", text: "Go on",
  title: "The writer goes on with the next sections; these questions stay open",
  onclick: (e) => send("go-on", e.currentTarget),
});

// A « plan » batch sent since the status last moved, with no question asked after it:
// scoping is over, the agent is writing the plan (or the model).
function planPending() {
  const since = state.status.since || "";
  return !openQuestions().length && state.comments.batches.some((b) => b.action === "plan" && b.sent >= since);
}

// What the agent writes once scoping ends: the model in a feature or a triage,
// the plan otherwise.
function scopingProduct() {
  return ["build-feature", "triage-code"].includes(state.workflow) ? "model" : "plan";
}

// Once what the button writes exists, the answers given since may change it: « Write »
// becomes « Rewrite ». A feature's planner drafts an outline before scoping ends, so
// there the button rewrites once the sections are written (as Session.has_written).
const rewriting = () => (state.workflow === "build-feature"
  ? Object.keys(state.sections).length > 0
  : (state.plan.outline || []).length > 0);

function renderScope() {
  const questions = state.questions || [];
  const open = openQuestions();
  for (const id of questionCards.keys()) if (!open.some((q) => q.id === id)) questionCards.delete(id);
  const box = $("#scope-questions");
  const cardsNow = open.map((q) => (atSection(q)
    ? el("button", { class: "questions-waiting", text: `${q.id} waits at the end of section ${numberOf(q.section)} →`,
                     onclick: () => { setTab(tabOf(q.section)); scrollToSection(q.section); } })
    : questionCard(q)));
  // Re-attaching a box would blur its text field: only when the list changed.
  const same = cardsNow.length === box.children.length
    && cardsNow.every((c, i) => box.children[i] === c || (c.tagName === "BUTTON" && box.children[i].textContent === c.textContent));
  if (!same) box.replaceChildren(...cardsNow);

  const closed = questions.filter((q) => q.status !== "open");
  const folded = $("#scope-answered");
  folded.hidden = !closed.length;
  const deferred = closed.filter((q) => q.status === "deferred").length;
  $("summary", folded).textContent = `answered (${closed.length - deferred})${deferred ? ` · deferred (${deferred})` : ""}`;
  $("ol", folded).replaceChildren(...closed.map((q) => el("li", {},
    el("div", { class: "q-text" }, el("span", { class: "num", text: q.id }), " ", q.text),
    el("div", { class: `q-reply ${q.status === "answered" ? "" : "dim"}` },
       q.status === "deferred"
         ? deferredText(q)
         : answerText(q.status === "skipped" ? { skipped: true } : q.answer || {}),
       q.answer?.from === "terminal" ? el("span", { class: "dim", text: " (in the terminal)" }) : null),
    el("span", { class: "t-chips", "data-question": q.id }))));
  $("#scope-empty").hidden = questions.length > 0 || state.status.phase === "scoping";
  // In a docs review the scope block sits at the top of the Doc tab, only while it has
  // questions, and holds them alone: no scoping to end, no grill.
  $("#scope").hidden = isDocsReview() && !questions.length;
  $(".scope-actions").hidden = isDocsReview();
  $(".scope-head").firstChild.nodeValue = isDocsReview() ? "questions" : "scope";
  annotateQuestions($("#scope"));

  const grill = $("#grill");
  grill.textContent = state.grilling ? "Stop grill" : "Grill me";
  grill.title = state.grilling ? "Stop the interview" : "The agent asks about every open decision, each with its suggestion, until none is left";
  const plan = $("#scope-plan");
  // A feature with a scoping section ends its scoping with « End scoping », in the scoping tab.
  plan.hidden = !(state.status.phase === "scoping" || open.length) || planPending() || paused() || hasScopingTab();
  $("#scope-go-on").hidden = !paused();
  plan.textContent = `${rewriting() ? "Rewrite" : "Write"} ${scopingProduct()}`;
  plan.title = rewriting()
    ? `Enough questions: the open ones count as skipped (a question waiting for its section stays open), and the agent revises the ${scopingProduct()} with your answers`
    : `Enough questions: the open ones count as skipped (a question waiting for its section stays open), and the agent writes the ${scopingProduct()}`;
}

$("#grill").addEventListener("click", (e) => send(state.grilling ? "stop-grill" : "grill", e.currentTarget));
$("#scope-plan").addEventListener("click", (e) => send("plan", e.currentTarget));
$("#scope-go-on").addEventListener("click", (e) => send("go-on", e.currentTarget));

/* The review pane keeps one line for the open agent questions: it opens the Plan tab
   at the scope block. */
function renderWaiting() {
  const n = openQuestions().length;
  const line = $("#questions-waiting");
  line.hidden = !n;
  line.textContent = `${n} question${n > 1 ? "s" : ""} waiting →`;
}

$("#questions-waiting").addEventListener("click", () => {
  const q = openQuestions()[0];
  if (q && atSection(q)) { setTab(tabOf(q.section)); scrollToSection(q.section); return; }
  setTab("plan");
  $("#scope").scrollIntoView({ block: "start", behavior: "smooth" });
});

/* ---------------- review pane ----------------
   The pane reads like a conversation, oldest at the top: the sent batches in time order
   (a batch answering an agent question shows the question, then the answer or « skipped »),
   then a line counting the open agent questions (they live in the scope block), then the
   drafts, the note and « Send » at the bottom. It stays
   scrolled to the bottom as content arrives, unless the user scrolled up. */

let reviewAtEnd = true;
$(".review").addEventListener("scroll", (e) => {
  const p = e.target;
  reviewAtEnd = p.scrollHeight - p.scrollTop - p.clientHeight < 24;
}, { passive: true });

// How a row anchor reads in the page: « triage k1 ».
const rowLabel = (id) => `${rowOf(id).kind} ${rowOf(id).id}`;

// Where a comment sits: its section's number, « doc set », the file name of its doc, or
// the row of a Doc tab table.
function whereOf(id) {
  if (id === DOC_SET) return "doc set";
  if (rowOf(id)) return rowLabel(id);
  const p = docPathOf(id);
  return p !== null ? p.slice(p.lastIndexOf("/") + 1) : `§${numberOf(id)}`;
}

function quoteLine(c) {
  if (c.question) return el("div", { class: "c-quote" }, el("span", { class: "num", text: "?" }), ` agent question ${c.question}`);
  const where = (c.section ? whereOf(c.section) : "·") + (c.fact ? ` · fact ${c.fact}` : "");
  const q = c.quote ? `« ${c.quote.length > 90 ? c.quote.slice(0, 90) + "…" : c.quote} »`
          : c.section ? "whole section" : "general";
  const open = () => {
    revealQuote(c);
    if (c.thread && threadsState.threads.some((t) => t.id === c.thread)) openPopover(c.thread);
  };
  return el("div", { class: "c-quote", onclick: c.thread ? open : () => revealQuote(c) },
    el("span", { class: "num", text: where }), " ", q,
    c.thread ? el("span", { class: "badge alt", text: `↳ ${c.thread}` }) : null);
}

function renderReview() {
  renderWaiting();
  $("#draft-count").textContent = drafts.length ? `· ${drafts.length} draft${drafts.length > 1 ? "s" : ""}` : "";
  // The review tab of the narrow layout carries the count of drafts, in sight from every tab.
  $('.tab[data-tab="review"]').textContent = drafts.length ? `review (${drafts.length})` : "review";
  renderDrafts();
  updateSend();

  const batches = state ? state.comments.batches : [];
  $("#history").replaceChildren(...(batches.length ? batches.map((b) =>
    el("div", { class: "batch" },
      el("div", { class: "b-head dim", text: `${b.id} · ${new Date(b.sent).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` }),
      b.note ? el("div", { class: "b-note", text: b.note }) : null,
      ...(b.answers || []).map((a) => answeredQuestion(a, b)),
      ...b.comments.map((c) => el("div", { class: `comment ${c.status}` },
        quoteLine(c),
        c.text || !c.thread ? el("div", { class: "c-text", text: c.text })
          : el("div", { class: "c-text dim", text: "the thread's conclusion" }),
        el("div", { class: "c-status" },
          el("span", { class: c.status === "resolved" ? "badge ok" : "badge", text: c.status === "resolved" ? "✓ resolved" : "waiting" }),
          c.reply ? el("span", { class: "c-reply", text: ` ${c.reply}` }) : null))))
  ) : [el("p", { class: "dim", text: "Nothing sent yet." })]));
  if (state) annotateQuestions($("#history"));
  const pane = $(".review");
  if (reviewAtEnd) pane.scrollTop = pane.scrollHeight;
}

/* An answered agent question in the history: its text, the answer (« skipped » for a
   skipped one), the agent's reply. */
const answerText = (a) => (a.skipped ? "skipped"
  : a.unclear ? ["I don't understand", a.note].filter(Boolean).join(" — ")
  : [(a.choices || []).join(", "), a.text].filter(Boolean).join(" — "));
// A deferred question: what the user said was missing, and where it will be asked again.
const deferredText = (q) => {
  const last = (q.unclear || []).slice(-1)[0] || {};
  const where = q.section ? `asked again after section ${numberOf(q.section)}` : "asked again once the model explains it";
  return [answerText({ unclear: true, note: last.note }), where].join(" · ");
};

function answeredQuestion(a, b) {
  const q = (state.questions || []).find((x) => x.id === a.question) || { id: a.question, text: "" };
  return el("div", { class: "question answered" },
    el("div", { class: "q-head" }, "Question from the agent ", el("span", { class: "dim", text: q.id })),
    q.text ? el("div", { class: "q-text", text: q.text }) : null,
    el("div", { class: `q-reply ${a.skipped || a.unclear ? "dim" : ""}`, text: answerText(a) },
       ...(a.threads || []).map((tid) => el("span", { class: "badge alt t-link", text: `↳ ${tid}`,
                                                       onclick: () => threadOf(tid) && openPopover(tid) }))),
    b.reply ? el("div", { class: "c-status" }, el("span", { class: "badge ok", text: "✓ resolved" }),
                 el("span", { class: "c-reply", text: ` ${b.reply}` })) : null);
}

function updateSend() {
  const note = $("#note").value.trim();
  const n = drafts.filter(ready).length;
  const btn = $("#send");
  btn.disabled = !n && !note;
  btn.textContent = n ? `Send ${n} comment${n > 1 ? "s" : ""}` : note ? "Send note" : "Send";
  if (state) renderStatus();
}

$("#note").addEventListener("input", () => { saveNote(); updateSend(); });
$("#note").addEventListener("blur", () => { if (noteTimer) saveNote(true); else loadDrafts(); });
$("#note").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
});
$("#send").addEventListener("click", () => send());

/* ---------------- drafts ----------------
   The drafts and the general note live in the session folder (drafts.json), not in the
   browser: every page open on the session, on any device, shows the same ones. Each
   change this page makes is saved at once (a typed text a moment after the last
   keystroke, and when its box is left); the server tells the other pages (event
   "drafts"), which fetch the file and redraw the review. The last edit of a draft wins:
   while you type in a draft's box (or the note), an edit from another page waits, and
   shows when you leave the box, unless you typed after it. A draft deleted on one page is
   gone on every page; an edit to it arriving later is dropped by the server. */

const SAVE_AFTER = 300; // ms after the last keystroke
const saveTimers = new Map(); // draft id -> its pending save
const unsaved = new Set(); // ids of drafts added here whose first save has not returned
const deletedHere = new Set(); // ids of drafts deleted from this page
const draftNodes = new Map(); // draft id -> its box in the review, built once
let noteTimer = null;

const draftBody = ({ section, quote, prefix, text, thread, fact }) => ({ section, quote, prefix, text, thread: thread || "", fact: fact || "" });

async function saveDraft(d, now = true) {
  clearTimeout(saveTimers.get(d.id));
  saveTimers.delete(d.id);
  if (!now) { saveTimers.set(d.id, setTimeout(() => saveDraft(d), SAVE_AFTER)); return; }
  unsaved.add(d.id);
  try {
    const r = await postJSON(`/api/s/${SLUG}/drafts/${encodeURIComponent(d.id)}`, draftBody(d), "PUT");
    if (!r.saved && !deletedHere.has(d.id)) {
      drafts = drafts.filter((x) => x.id !== d.id);
      toast("This draft was deleted on another page");
      afterDrafts();
    }
  } catch (e) { toast(`Could not save the draft: ${e.message}`); }
  unsaved.delete(d.id);
}

async function deleteDraft(d) {
  clearTimeout(saveTimers.get(d.id));
  saveTimers.delete(d.id);
  deletedHere.add(d.id);
  drafts = drafts.filter((x) => x.id !== d.id);
  afterDrafts();
  try { await postJSON(`/api/s/${SLUG}/drafts/${encodeURIComponent(d.id)}`, {}, "DELETE"); }
  catch (e) { toast(`Could not delete the draft: ${e.message}`); }
}

async function saveNote(now = false) {
  clearTimeout(noteTimer);
  noteTimer = null;
  if (!now) { noteTimer = setTimeout(() => saveNote(true), SAVE_AFTER); return; }
  try { await postJSON(`/api/s/${SLUG}/note`, { note: $("#note").value }, "PUT"); }
  catch (e) { toast(`Could not save the note: ${e.message}`); }
}

// The draft whose box has the focus, if any: its text stays as typed.
const editingDraft = () => document.activeElement?.closest?.("#drafts .draft")?.dataset.draft || null;

/* Takes the drafts file in: the server's drafts, in its order, but the one being typed
   in keeps its text, and one added here whose save has not returned stays. */
async function loadDrafts() {
  let data;
  try {
    const r = await fetch(`/api/s/${SLUG}/drafts`);
    if (!r.ok) return;
    data = await r.json();
  } catch (e) { return; }
  const editing = editingDraft();
  const mine = new Map(drafts.map((d) => [d.id, d]));
  const next = data.drafts.map((d) => {
    const here = mine.get(d.id);
    if (here && (d.id === editing || saveTimers.has(d.id))) return here;
    return here ? Object.assign(here, d) : d;
  });
  for (const d of drafts) if (unsaved.has(d.id) && !next.some((x) => x.id === d.id)) next.push(d);
  drafts = next;
  const note = $("#note");
  if (document.activeElement !== note && !noteTimer) note.value = data.note;
  afterDrafts();
}

function afterDrafts() {
  renderReview();
  if (state) { applyHighlights(); renderPopover(); }
}

/* The drafts in the review, each box kept across redraws: one being typed in is never
   re-attached (that would take its focus), and keeps the text typed. */
function renderDrafts() {
  const box = $("#drafts");
  const editing = editingDraft();
  for (const id of draftNodes.keys()) if (!drafts.some((d) => d.id === id)) { draftNodes.get(id).remove(); draftNodes.delete(id); }
  drafts.forEach((d, k) => {
    let node = draftNodes.get(d.id);
    if (!node) {
      const ta = el("textarea", { class: "c-text", rows: "2",
                                  placeholder: d.thread ? "What should change, after this thread? (optional)" : "" });
      ta.addEventListener("input", () => { node._draft.text = ta.value; saveDraft(node._draft, false); updateSend(); });
      // Leaving the box: a pending keystroke is saved (it wins), else the file's text shows.
      ta.addEventListener("blur", () => { if (saveTimers.has(node._draft.id)) saveDraft(node._draft); else loadDrafts(); });
      node = el("div", { class: "comment draft", "data-draft": d.id }, quoteLine(d), ta,
        el("button", { class: "c-del", text: "×", title: "Delete", onclick: () => deleteDraft(node._draft) }));
      draftNodes.set(d.id, node);
    }
    node._draft = d;
    node.replaceChild(quoteLine(d), node.firstChild);
    const ta = $("textarea", node);
    if (d.id !== editing && ta.value !== d.text) ta.value = d.text;
    if (box.children[k] !== node) box.insertBefore(node, box.children[k] || null);
  });
}

/* The drafts and the note this browser kept before the drafts file go to the session
   folder, after those already there, the first time it opens the session. */
async function moveBrowserDrafts() {
  const old = loadJSON(DRAFTS_KEY, []), note = loadJSON(NOTE_KEY, "");
  if (!(Array.isArray(old) && old.length) && !String(note || "").trim()) return;
  try {
    await postJSON(`/api/s/${SLUG}/drafts/import`, { drafts: Array.isArray(old) ? old : [], note: String(note || "") });
    try { localStorage.removeItem(DRAFTS_KEY); localStorage.removeItem(NOTE_KEY); } catch (e) { /* private mode */ }
  } catch (e) { toast(`Could not move this browser's drafts: ${e.message}`); }
}

/* A batch from « Send », an approval button, a scope block button or a Doc tab request
   (`button`); `extra` carries then_pr or the path of a rewrite request. */
const SCOPE_TOASTS = { plan: "Scoping ended", grill: "Grill started", "stop-grill": "Grill stopped",
                       "go-on": "The writer goes on", missing: "Asked what's missing", "end-scoping": "Scoping ended" };
// The toast of a request sent from the Doc tab, from the `extra` it was sent with.
const DOC_TOASTS = { "rewrite-readme": (extra) => `Rewrite of ${extra.path} requested`,
                     "write-lexicon": () => "Repo lexicon requested" };

async function send(action = "", button = null, extra = {}) {
  const approval = Object.values(APPROVALS).find((a) => a.action === action);
  const btn = button || (approval ? buttonOf(approval) : $("#send"));
  if (btn.disabled) return;
  btn.disabled = true;
  // The batch carries the texts as typed: a save still pending would bring a sent draft back.
  const pending = drafts.filter((d) => saveTimers.has(d.id));
  for (const d of pending) { clearTimeout(saveTimers.get(d.id)); saveTimers.delete(d.id); }
  clearTimeout(noteTimer);
  noteTimer = null;
  const r = await fetch(`/api/s/${SLUG}/batch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      action,
      ...(extra.then_pr ? { then_pr: true } : {}),
      ...(extra.path ? { path: extra.path } : {}),
      note: $("#note").value,
      comments: drafts.map(({ section, quote, prefix, text, thread, fact }) => ({ section, quote, prefix, text, thread, fact: fact || "" })),
      drafts: drafts.map((d) => d.id),
    }),
  });
  btn.disabled = false;
  if (!r.ok) {
    toast(`Send failed: ${(await r.json()).detail}`);
    pending.forEach((d) => saveDraft(d));
    saveNote(true);
    updateSend();
    return;
  }
  const b = await r.json();
  // The server cleared the drafts the batch carried and the note, on every page.
  drafts = [];
  $("#note").value = "";
  await load();
  const toastText = approval && extra.then_pr && approval.also ? approval.also.toast : approval ? approval.toast : "";
  sentToast(toastText || SCOPE_TOASTS[action] || DOC_TOASTS[action]?.(extra) || `Sent ${b.id} to the session`);
}

/* ---------------- divider ----------------
   The border between the workspace and the review pane is a divider: dragging it sets
   the pane's width, from 300 px to 70 % of the window, remembered in this browser.
   A double-click goes back to the default width. */

const divider = $("#divider");
const clampWidth = (px) => Math.round(Math.max(300, Math.min(px, innerWidth * 0.7)));

function setReviewWidth(px) {
  const layout = $(".layout");
  if (px == null) layout.style.removeProperty("--review-width");
  else layout.style.setProperty("--review-width", `${clampWidth(px)}px`);
  positionPopover();
}

setReviewWidth(isNarrow() ? null : loadJSON(WIDTH_KEY, null));
divider.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  divider.setPointerCapture(e.pointerId);
  divider.classList.add("dragging");
  document.body.classList.add("resizing");
});
divider.addEventListener("pointermove", (e) => {
  if (divider.hasPointerCapture(e.pointerId)) setReviewWidth($(".layout").getBoundingClientRect().right - e.clientX);
});
divider.addEventListener("pointerup", (e) => {
  if (!divider.hasPointerCapture(e.pointerId)) return;
  divider.releasePointerCapture(e.pointerId);
  divider.classList.remove("dragging");
  document.body.classList.remove("resizing");
  saveJSON(WIDTH_KEY, $(".review").getBoundingClientRect().width);
});
divider.addEventListener("dblclick", () => { saveJSON(WIDTH_KEY, null); setReviewWidth(null); });
// A smaller window keeps the pane within 70 % of it.
addEventListener("resize", () => { if (!isNarrow()) setReviewWidth(loadJSON(WIDTH_KEY, null)); });

/* ---------------- side threads ----------------
   A thread opens in a popover on its passage. One is shown at a time; its × button, Esc
   or a click anywhere else closes it (the thread stays), and a click on the passage
   (highlighted) opens it again. A thread with no passage to sit on (a whole-section thread, a general one, or one whose passage was
   rewritten) gets a chip instead: in its section's heading, in the top bar for a
   general one, or in its question's box for a thread opened on an agent question. The popover follows its anchor when the view scrolls, and hides while the
   anchor is out of sight.

   A thread's card is built once and then patched in place (head, messages, footer
   state), so a streaming reply never takes the focus or the text of its reply box. */

async function loadThreads() {
  const r = await fetch(`/api/s/${SLUG}/threads`);
  if (!r.ok) return;
  threadsState = await r.json();
  for (const id of cards.keys()) if (!threadsState.threads.some((t) => t.id === id)) cards.delete(id);
  if (state) { applyHighlights(); renderThreadChips(); applyDrafts(); }
  renderPopover();
}

/* « use as answer » on a thread opened on an open agent question: a turn that drafts the
   user's answer from the discussion (the reply's `draft`, read by the server), which fills
   the question's box once, to edit before « Validate ». */
const appliedDrafts = new Set(); // "<thread>@<reply time>": drafts already put in their box
function applyDrafts() {
  for (const t of threadsState.threads) {
    const reply = t.messages[t.messages.length - 1];
    const key = `${t.id}@${reply?.at}`;
    if (t.state !== "idle" || !reply?.draft || appliedDrafts.has(key)) continue;
    appliedDrafts.add(key);
    const q = openQuestions().find((x) => x.id === t.question);
    if (!q) continue;
    const { choices, text } = reply.draft;
    if (!choices.length && !text) { toast(`${t.id} could not draft an answer to ${q.id}`); continue; }
    questionCard(q)._fill(reply.draft);
    toast(`${q.id}: answer drafted from ${t.id}, check it and Validate`, 4000);
  }
}

async function draftAnswer(tid) {
  try {
    await postJSON(`/api/s/${SLUG}/threads/${tid}/draft`, {});
    await loadThreads();
  } catch (e) { toast(`Could not draft the answer: ${e.message}`); }
}

async function postJSON(url, body, method = "POST") {
  const r = await fetch(url, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail);
  return data;
}

async function askThread() {
  const c = $("#composer");
  const text = $("textarea", c).value.trim();
  if (!text) return;
  const { section, quote, prefix, question = "", fact = "" } = c._target;
  try {
    const t = await postJSON(`/api/s/${SLUG}/threads`, { section, quote, prefix, question, fact, text });
    closeComposer();
    getSelection().removeAllRanges();
    popThread = t.id;
    await loadThreads();
  } catch (e) { toast(`Could not start the thread: ${e.message}`); }
}

$("#new-thread").addEventListener("click", (e) =>
  openComposer({ section: "", quote: "", prefix: "", rect: e.target.getBoundingClientRect() }, "ask"));

const threadOf = (id) => threadsState.threads.find((t) => t.id === id);
const sentThreads = () => new Set((state ? state.comments.batches : []).flatMap((b) => [
  ...b.comments.map((c) => c.thread), ...(b.answers || []).flatMap((a) => a.threads || [])]).filter(Boolean));

/* The threads without a passage on the page, as chips: a passage of a Markdown section
   (threadRanges) or one a frame found (placed) takes the chip away. */
function renderThreadChips() {
  const placed = new Set(threadRanges.map(([t]) => t.id));
  const chip = (t) => el("button", {
    class: `t-chip ${t.state === "running" ? "running" : t.state === "error" ? "error" : ""}`,
    "data-thread": t.id, text: t.id, title: (t.messages[0] || {}).text || "",
    onclick: (e) => { e.stopPropagation(); popThread === t.id ? closePopover() : openPopover(t.id); },
  });
  document.querySelectorAll(".t-chips[data-section]").forEach((box) =>
    box.replaceChildren(...threadsState.threads
      .filter((t) => t.section === box.dataset.section && !t.question && !placed.has(t.id)
        && !frames.get(t.section)?.placed?.has(t.id)).map(chip)));
  document.querySelectorAll(".t-chips[data-question]").forEach((box) =>
    box.replaceChildren(...threadsState.threads.filter((t) => t.question === box.dataset.question).map(chip)));
  $("#general-threads").replaceChildren(...threadsState.threads.filter((t) => !t.section && !t.question).map(chip));
}

function threadAt(x, y) {
  for (const [t, r] of threadRanges) {
    for (const b of r.getClientRects()) {
      if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) return t;
    }
  }
  return null;
}

/* Where the popover sits: under the thread's passage, else under its chip. */
function anchorRect(id) {
  const hit = threadRanges.find(([t]) => t.id === id);
  if (hit) return hit[1].getBoundingClientRect();
  const inFrame = frameThreads.get(id);
  if (inFrame && inFrame.f.isConnected) return pageRect(inFrame.f, inFrame.rect);
  const chip = document.querySelector(`.t-chip[data-thread="${CSS.escape(id)}"]`);
  return chip ? chip.getBoundingClientRect() : null;
}

function openPopover(id) {
  const t = threadOf(id);
  if (!t) return;
  if (t.section && !t.question && !t.quote.startsWith("plan · ")) {
    openSection(t.section);
    openItemOf(t.section);
  }
  popThread = id;
  renderPopover();
}

function closePopover() {
  if (popThread) frameThreads.delete(popThread);
  popThread = null;
  $("#thread-pop").hidden = true;
}

function renderPopover() {
  const pop = $("#thread-pop");
  const t = popThread && threadOf(popThread);
  if (!t) { closePopover(); return; }
  const card = threadCard(t);
  patchCard(t, card);
  if (pop.firstChild !== card.root) pop.replaceChildren(card.root, threadGrip); // re-attaching would blur the reply box
  pop.hidden = false;
  positionPopover();
}

function positionPopover() {
  const pop = $("#thread-pop");
  if (!popThread || pop.hidden) return;
  if (isNarrow()) return; // docked across the bottom (app.css)
  const r = anchorRect(popThread);
  const visible = r && r.width > 0 && r.bottom > 0 && r.top < innerHeight;
  pop.style.visibility = visible ? "visible" : "hidden";
  if (!visible) return;
  const h = pop.offsetHeight;
  const w = pop.offsetWidth;
  const below = r.bottom + 6;
  const top = below + h <= innerHeight - 8 || r.top - h - 6 < 8 ? below : r.top - h - 6;
  pop.style.top = `${Math.max(8, Math.min(top, innerHeight - h - 8))}px`;
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
}

/* The popover's bottom right corner is a grip: dragging it sets the thread's width and
   height, kept within the window and remembered in this browser for every thread. A
   double-click goes back to the default size. The docked thread of the narrow layout
   has no grip (app.css). */
const threadGrip = el("div", { class: "t-grip", title: "drag to resize, double-click to reset" });

function setThreadSize(size) {
  const pop = $("#thread-pop");
  const sized = !!size && !isNarrow();
  pop.classList.toggle("sized", sized);
  if (!sized) { pop.style.width = pop.style.height = ""; return; }
  const r = pop.getBoundingClientRect();
  pop.style.width = `${Math.round(Math.max(280, Math.min(size.width, innerWidth - r.left - 8)))}px`;
  pop.style.height = `${Math.round(Math.max(160, Math.min(size.height, innerHeight - r.top - 8)))}px`;
}

setThreadSize(loadJSON(THREAD_SIZE_KEY, null));
threadGrip.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  threadGrip.setPointerCapture(e.pointerId);
  document.body.classList.add("resizing-corner");
});
threadGrip.addEventListener("pointermove", (e) => {
  if (!threadGrip.hasPointerCapture(e.pointerId)) return;
  const r = $("#thread-pop").getBoundingClientRect();
  setThreadSize({ width: e.clientX - r.left, height: e.clientY - r.top });
});
threadGrip.addEventListener("pointerup", (e) => {
  if (!threadGrip.hasPointerCapture(e.pointerId)) return;
  threadGrip.releasePointerCapture(e.pointerId);
  document.body.classList.remove("resizing-corner");
  const r = $("#thread-pop").getBoundingClientRect();
  saveJSON(THREAD_SIZE_KEY, { width: r.width, height: r.height });
  positionPopover();
});
threadGrip.addEventListener("dblclick", () => { saveJSON(THREAD_SIZE_KEY, null); setThreadSize(null); positionPopover(); });

document.querySelectorAll(".view").forEach((v) => v.addEventListener("scroll", positionPopover, { passive: true }));
addEventListener("resize", positionPopover);
document.addEventListener("mousedown", (e) => {
  if (popThread && !e.target.closest("#thread-pop, #composer")) closePopover();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && popThread && !e.target.closest("#composer")) closePopover();
});
// The passage of a thread is clickable: say so with the cursor.
docViews().forEach((v) => v.addEventListener("mousemove", (e) => {
  v.style.cursor = threadAt(e.clientX, e.clientY) ? "pointer" : "";
}));

function threadCard(t) {
  if (cards.has(t.id)) return cards.get(t.id);
  const ta = el("textarea", { class: "c-text", rows: "2", placeholder: isTouch() ? "Reply" : "Reply  (↵ to send, ⇧↵ for a new line, Esc to close)" });
  const card = {
    root: el("div", { class: "thread-card" }),
    head: el("div", { class: "t-head" }),
    msgs: el("div", { class: "t-msgs" }),
    error: el("div", { class: "t-error error" }),
    ta,
    reply: el("button", { class: "btn primary", text: "Reply", onclick: () => replyThread(t.id) }),
    stop: el("button", { class: "btn", text: "Stop", onclick: () => postJSON(`/api/s/${SLUG}/threads/${t.id}/stop`, {}) }),
    batch: el("button", { class: "btn", text: "→ batch", title: "Add a draft comment that points to this thread",
                          onclick: () => threadToBatch(t.id) }),
    del: el("button", { class: "btn t-delete", text: "Delete", onclick: () => deleteThread(t.id) }),
    draft: el("button", { class: "btn", text: "use as answer",
                          title: "Draft your answer to the question from this discussion, in its box, to check before Validate",
                          onclick: () => draftAnswer(t.id) }),
  };
  ta.addEventListener("keydown", (e) => {
    if (sendsOnEnter(e)) { e.preventDefault(); replyThread(t.id); }
  });
  card.foot = el("div", { class: "t-foot" }, ta, el("div", { class: "t-actions" }, card.del, card.batch, card.draft, card.stop, card.reply));
  card.root.append(card.head, card.msgs, card.error, card.foot);
  cards.set(t.id, card);
  return card;
}

function patchCard(t, card) {
  const running = t.state === "running";
  card.head.replaceChildren(
    el("div", { class: "t-title" },
      el("span", { class: "num", text: t.id }),
      running ? el("span", { class: "badge accent writing", text: t.activity || "running" })
      : t.state === "error" ? el("span", { class: "badge flag", text: "error" }) : null,
      el("button", { class: "t-close", text: "×", title: "Close (the thread stays, reopen it from its passage or chip)",
                     onclick: closePopover })),
    quoteLine(t));
  card.error.hidden = !t.error;
  card.error.textContent = t.error;
  const sig = JSON.stringify(t.messages.map((m) => [m.text.length, !!m.stopped]));
  if (card.msgs.dataset.sig !== sig) {
    const m = card.msgs;
    const atEnd = m.scrollHeight - m.scrollTop - m.clientHeight < 24;
    m.dataset.sig = sig;
    m.replaceChildren(...t.messages.map((msg) => {
      const body = el("div", { class: `t-msg ${msg.role}` });
      if (msg.role === "user") body.textContent = msg.text;
      else body.innerHTML = msg.html + (msg.stopped ? "<p class=\"dim\">(stopped)</p>" : "");
      return body;
    }));
    typesetMath(m);
    linkCitations(m);
    if (atEnd) m.scrollTop = m.scrollHeight;
  }
  const sent = sentThreads().has(t.id);
  const drafted = drafts.some((d) => d.thread === t.id);
  card.reply.disabled = running;
  card.stop.hidden = !running;
  card.batch.disabled = sent || drafted;
  card.batch.textContent = sent ? "sent" : drafted ? "in the batch" : "→ batch";
  // A thread on an agent question reaches the session with the answer, not as a comment.
  const open = t.question && openQuestions().some((q) => q.id === t.question);
  card.batch.hidden = !!t.question;
  card.draft.hidden = !open;
  card.draft.disabled = running || !t.messages.some((m) => m.role === "assistant" && m.text.trim());
  // Only a thread that led to nothing can go: the session reads the ones a sent comment points to.
  card.del.hidden = sent;
  card.del.disabled = running;
  card.del.title = running ? "Stop the thread first" : "Delete this thread";
}

async function replyThread(tid) {
  const card = cards.get(tid);
  const text = card.ta.value.trim();
  if (!text || card.reply.disabled) return;
  card.reply.disabled = true;
  try {
    await postJSON(`/api/s/${SLUG}/threads/${tid}`, { text });
    card.ta.value = "";
    await loadThreads();
  } catch (e) { toast(`Reply failed: ${e.message}`); card.reply.disabled = false; }
}

async function deleteThread(tid) {
  if (!confirm(`Delete thread ${tid}? Its conversation is lost.`)) return;
  try {
    await postJSON(`/api/s/${SLUG}/threads/${tid}`, {}, "DELETE");
  } catch (e) { toast(`Could not delete: ${e.message}`); return; }
  for (const d of drafts.filter((x) => x.thread === tid)) deleteDraft(d);
  closePopover();
  renderReview();
  await loadThreads();
}

/* The conclusion of a thread reaches the main session as an ordinary comment, anchored
   where the thread was and carrying its id, so the session can read the thread, and the
   id of the missing fact it was opened on, if any. Its text is optional: without one,
   the thread's conclusion is the comment. */
function threadToBatch(tid) {
  const t = threadOf(tid);
  const d = { id: crypto.randomUUID(), section: t.section, quote: t.quote, prefix: t.prefix, text: "", thread: tid,
              ...(t.fact ? { fact: t.fact } : {}) };
  drafts.push(d);
  saveDraft(d);
  renderReview();
  applyHighlights();
  renderPopover();
}

/* ---------------- export, publish, tooltips ---------------- */

$("#export").addEventListener("click", async () => {
  const r = await fetch(`/api/s/${SLUG}/export`, { method: "POST" });
  const body = await r.json();
  toast(r.ok ? `Exported to explanations/${body.name}` : `Export failed: ${body.detail}`, 5000);
});

/* The publish buttons follow the publish record (state.published: {url, at, out_of_date}
   or null): « Publish » when never published; « Published <date> » (copies the link) and
   « Unpublish » when published; « Republish · changed since <date> » and « Unpublish »
   when out of date. A code session is never published, so they are hidden in one. */
let publishing = false;  // a publish or unpublish is running

function localDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function renderPublish() {
  const pub = $("#publish"), unpub = $("#unpublish");
  const code = state.plan.kind === "code";
  const rec = state.published;
  pub.hidden = code;
  unpub.hidden = code || !rec;
  if (publishing) return;  // keep « Publishing… » until the request ends
  pub.disabled = unpub.disabled = false;
  if (!rec) {
    pub.textContent = "Publish";
    pub.title = "Publish the explanation as a page on the web and copy its link";
  } else if (rec.out_of_date) {
    pub.textContent = `Republish · changed since ${localDate(rec.at)}`;
    pub.title = `Publish again at ${rec.url}`;
  } else {
    pub.textContent = `Published ${localDate(rec.at)}`;
    pub.title = `Copy the link: ${rec.url}`;
  }
}

async function copyLink(url) {
  try { await navigator.clipboard.writeText(url); return true; } catch (e) { return false; }
}

$("#publish").addEventListener("click", async () => {
  const rec = state.published;
  if (rec && !rec.out_of_date) {
    toast(await copyLink(rec.url) ? `Link copied: ${rec.url}` : rec.url, 5000);
    return;
  }
  const pub = $("#publish"), unpub = $("#unpublish");
  publishing = true;
  pub.disabled = unpub.disabled = true;
  pub.textContent = "Publishing…";
  try {
    const r = await fetch(`/api/s/${SLUG}/publish`, { method: "POST" });
    const body = await r.json();
    if (r.ok) {
      const copied = await copyLink(body.url);
      toast(`Published: ${body.url}${copied ? " — link copied" : ""}`, 6000);
    } else toast(`Publish failed: ${body.detail}`, 8000);
  } catch (e) {
    toast(`Publish failed: ${e.message}`, 8000);
  } finally {
    publishing = false;
    await load();  // the new record, without waiting for the change stream
  }
});

$("#unpublish").addEventListener("click", async () => {
  const rec = state.published;
  if (!rec || !confirm(`Take ${rec.url} off the web? The repo's history keeps the old version.`)) return;
  const pub = $("#publish"), unpub = $("#unpublish");
  publishing = true;
  pub.disabled = unpub.disabled = true;
  try {
    const r = await fetch(`/api/s/${SLUG}/unpublish`, { method: "POST" });
    const body = await r.json();
    toast(r.ok ? `Unpublished: ${rec.url}` : `Unpublish failed: ${body.detail}`, r.ok ? 5000 : 8000);
  } catch (e) {
    toast(`Unpublish failed: ${e.message}`, 8000);
  } finally {
    publishing = false;
    await load();  // the new record, without waiting for the change stream
  }
});

/* ---------------- notices ----------------
   The home-screen app can show a notice when a session starts waiting for you (push.py),
   on the lock screen too. « notices » in the ⋯ menu turns them on for this phone: the
   phone asks for your permission, the app installs its service worker (/sw.js) and gives
   the server a subscription; every session of the server then notifies this phone. Only
   the home-screen app offers it: a page open in the browser (an iPhone's, the Mac's)
   cannot receive notices. Tapped again, it turns them off. */
const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const canNotify = () => standalone() && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
const b64 = (s) => {
  const raw = atob((s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

async function noticeSubscription() {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

async function renderNotices() {
  const btn = $("#notices");
  btn.hidden = !canNotify();
  if (btn.hidden) return;
  const on = Notification.permission === "granted" && !!(await noticeSubscription().catch(() => null));
  btn.textContent = on ? "notices: on" : "notices: off";
  btn.title = on ? "This phone gets a notice when a session waits for you; tap to turn them off"
                 : "Get a notice on this phone when a session waits for you";
  btn.dataset.on = on ? "1" : "";
}

$("#notices").addEventListener("click", async () => {
  const btn = $("#notices");
  try {
    if (btn.dataset.on) {
      const sub = await noticeSubscription();
      if (sub) { await postJSON("/api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
      toast("Notices off on this phone");
    } else {
      if (await Notification.requestPermission() !== "granted") { toast("Notices are not allowed on this phone"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
      const { key } = await (await fetch("/api/push/key")).json();
      const sub = (await reg.pushManager.getSubscription())
        || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
      await postJSON("/api/push/subscribe", sub.toJSON());
      toast("Notices on: this phone hears when a session waits for you");
    }
  } catch (e) { toast(`Notices: ${e.message}`, 6000); }
  renderNotices();
});
renderNotices();

/* The tip under a word: a lexicon entry's (`term`, its index in `lexicon`, the model's
   unless given) or a plain text (`text`). */
function showTip(text, term, r, lexicon = state.plan.lexicon) {
  const tip = $("#tip");
  if (term !== null) {
    const entry = lexicon[term];
    if (!entry) return;
    tip.replaceChildren(el("div", { class: "tip-term", text: entry.term }));
    const body = el("div", { class: "tip-body" });
    body.innerHTML = entry.tip_html;
    tip.append(body);
    typesetMath(tip);
  } else tip.textContent = text;
  tip.hidden = false;
  tip.style.top = `${window.scrollY + r.bottom + 4}px`;
  tip.style.left = `${Math.min(r.left, innerWidth - 360)}px`;
}

document.addEventListener("mouseover", (e) => {
  if (isTouch()) return; // a tap shows it (see "taps")
  const t = e.target.closest("[data-tip], [data-term]");
  if (!t) { $("#tip").hidden = true; return; }
  showTip(t.dataset.tip, t.dataset.term !== undefined ? Number(t.dataset.term) : null, t.getBoundingClientRect(), lexiconOf(t));
});

// ?static skips the live stream (headless rendering never finishes while it is open).
moveBrowserDrafts().then(load).then(loadDrafts).then(loadThreads).then(() => { if (!new URLSearchParams(location.search).has("static")) connect(); });
