/* view-concept — the session page.

   Tabs share the main space: the plan (the scope block with the agent questions, outline,
   model changes, lexicon), the explanation (one block per explanation section) and, in a
   branch review that has reached the refactoring step, the refactor tab (the refactor
   sections, Part 2); the review pane (a conversation: sent batches and answered agent
   questions, a line counting the open ones, then the draft comments) stays on the right. The page never edits the explanation: the agent
   writes the files, the server streams "changed", the page re-fetches. The page writes
   batches of comments, and side threads: separate read-only agent conversations run by
   the server, streamed through "threads" events. A thread shows in a popover on its
   passage (see "side threads" below).

   A comment is anchored by (section id, quoted text, a few characters of prefix). The
   quote is searched again after every re-render, so an anchor survives edits elsewhere
   in the section and silently disappears when its passage is rewritten. */

"use strict";

const SLUG = decodeURIComponent(location.pathname.split("/").pop());
const DRAFTS_KEY = `view-concept:drafts:${SLUG}`;
const NOTE_KEY = `view-concept:note:${SLUG}`;
const WIDTH_KEY = "view-concept:review-width"; // per browser, for every session

let state = null;        // last payload from /api/s/<slug>
let planChanged = false;
let drafts = loadJSON(DRAFTS_KEY, []);
let pendingSelection = null;
let tab = null;          // "plan" | "doc" | "refactor"
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
    $("#doc").replaceChildren(el("p", { class: "error", text: `Could not load: ${(await r.json()).detail}` }));
    return;
  }
  const next = await r.json();
  if (state && JSON.stringify(state.plan) !== JSON.stringify(next.plan)) planChanged = true;
  state = next;
  render();
}

function connect() {
  const es = new EventSource(`/api/s/${SLUG}/events`);
  const live = $("#live");
  es.addEventListener("hello", () => { live.textContent = "live"; live.className = "live on"; });
  es.addEventListener("changed", () => load());
  es.addEventListener("threads", () => loadThreads());
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

/* Part 2 of a branch review, written in the refactoring step, is made of refactor sections
   (sections with "part": 2): they are read in their own tab, "refactor"; every other
   section is an explanation section, in the explanation. Both tabs are rendered into
   their own view, with the same section blocks. */
const isPart2 = (id) => (state.plan.outline.find((s) => s.id === id) || {}).part === 2;
const tabOf = (id) => (isPart2(id) ? "refactor" : "doc");
const hasRefactorTab = () => state.plan.outline.some((s) => s.part === 2);
const docViews = () => [$("#doc"), $("#refactor")];
// Rewritten since its highlight baseline: the text at the last batch sent, or at « mark
// read » (the server compares with seen.json).
const isUpdated = (id) => !!(state.sections[id] || {}).updated;

function render() {
  const { plan } = state;
  // A mark in the tab title while an agent question waits, to be seen from another window.
  document.title = `${openQuestions().length ? "● " : ""}${plan.title} · view-concept`;
  $("#title").textContent = plan.title;
  renderListening();
  renderStatus();
  followSession();
  renderPlan();
  renderDoc();
  renderReview();
  renderPopover(); // a sent batch changes what the open thread offers
}

/* ---------------- tabs ----------------
   The plan, the explanation and the refactor tab share one space; one is shown at a
   time. The refactor tab exists only once a section is in Part 2. The tab follows the
   session at the moments that matter — scoping starting (its questions are in the scope
   block, on the Plan tab), the plan waiting for approval, the writing starting (in the
   tab of the section being written) — and otherwise stays where the user put it. A model waiting for approval does not move it, nor does a PR waiting to
   be created: « Approve model » sits at the end of the explanation, where the model is
   read, and « Create PR » at the end of the refactor tab. */

function setTab(name) {
  if (name === "refactor" && !hasRefactorTab()) name = "doc";
  tab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  $("#sel-actions").hidden = true;
  renderMermaid($(`.view[data-view="${name}"]`));
  positionPopover();
}

function followSession() {
  const phase = state.status.phase;
  const onPlan = ["scoping", "awaiting-approval"].includes(phase);
  if (tab === null) setTab(Object.keys(state.sections).length && !onPlan ? "doc" : "plan");
  else if (phase !== lastPhase) {
    if (onPlan) setTab("plan");
    if (phase === "writing") setTab(tabOf(state.status.section));
  }
  lastPhase = phase;
  $('.tab[data-tab="refactor"]').hidden = !hasRefactorTab();
  if (tab === "refactor" && !hasRefactorTab()) setTab("doc");
  // In a branch review, Part 1 is the model of the branch, so its tab is named after it.
  const docLabel = state.workflow === "view-branch" ? "model" : "explanation";
  $('.tab[data-tab="doc"]').title = `${docLabel[0].toUpperCase()}${docLabel.slice(1)} (2)`;
  for (const [name, label] of [["doc", docLabel], ["refactor", "refactor"]]) {
    const n = Object.keys(state.sections).filter((id) => isUpdated(id) && tabOf(id) === name).length;
    const writing = phase === "writing" && tabOf(state.status.section) === name;
    $(`.tab[data-tab="${name}"]`).replaceChildren(...[label,
      n ? el("span", { class: "badge new", text: `${n} updated` }) : null,
      writing ? el("span", { class: "badge accent writing", text: "writing" }) : null].filter(Boolean));
  }
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
document.addEventListener("keydown", (e) => {
  if (e.target.closest("textarea, input") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "1") setTab("plan");
  if (e.key === "2") setTab("doc");
  if (e.key === "3" && hasRefactorTab()) setTab("refactor");
});

/* ---------------- status + approvals ---------------- */

/* The agent is listening while a watch runs for the session (the server reads the watch's
   heartbeat). It says whether a batch is read now; the « live » dot only says whether
   the page is connected to the server. */
function renderListening() {
  const l = $("#listening");
  l.className = `listening ${state.listening ? "on" : "off"}`;
  l.textContent = state.listening ? "● Agent listening" : "○ Agent not listening";
}
// What a successful send says when no watch reads it: the batch waits in the inbox.
const NOT_LISTENING = "The agent isn't listening: write anything in the terminal and it will read this batch";
const sentToast = (msg) => toast(state.listening ? msg : NOT_LISTENING, state.listening ? 3000 : 8000);

const writingId = () => (state.status.phase === "writing" ? state.status.section : "");

/* "awaiting-answer" waits on the open agent questions, answered from their boxes in the
   scope block (see "agent questions" below), so it has no button here. */
const QUESTION_LABELS = { ready: "question · waiting for your answer", sent: "answered · the agent is reading it" };

/* Three phases wait for the user: the plan of an explanation ("awaiting-approval"), the
   model of a branch review at the end of model consolidation ("awaiting-model", set by the
   view-branch skill only), and the opening of its PR once refactoring is written
   ("awaiting-pr", view-branch too).
   Each is answered from the page by a batch carrying the phase's action, draft comments
   included. Until the agent moves the status on, the page says the answer is on its way.
   « Approve plan » sits at the top of the Plan tab, and the page switches to it.
   « Approve model » sits at the end of the explanation, after the last section of Part 1,
   where the model is read; « Create PR » at the end of the refactor tab. The page does not
   switch tabs for them. */
const docButton = el("button", { id: "doc-approve", class: "btn primary approve doc-approve", hidden: true });
const prButton = el("button", { id: "pr-create", class: "btn primary approve doc-approve", hidden: true });
const APPROVALS = {
  "awaiting-approval": { action: "approve-plan", label: "Approve plan", toast: "Plan approved",
                         ready: "plan ready · waiting for your approval", sent: "plan approved · the agent is starting" },
  "awaiting-model": { action: "approve-model", label: "Approve model", toast: "Model approved", button: docButton,
                      ready: "model ready · waiting for your approval", sent: "model approved · the agent is implementing" },
  "awaiting-pr": { action: "create-pr", label: "Create PR", toast: "PR requested", button: prButton,
                   ready: "refactoring written · waiting for you to create the PR",
                   sent: "PR requested · the agent is opening it" },
};
const buttonOf = (approval) => approval.button || $("#approve");

function approvalPending() {
  const approval = APPROVALS[state.status.phase];
  if (!approval) return false;
  const since = state.status.since || "";
  return state.comments.batches.some((b) => b.action === approval.action && b.sent >= since);
}

function renderStatus() {
  const { phase, section, message } = state.status;
  const approval = APPROVALS[phase];
  const asking = ["scoping", "awaiting-answer"].includes(phase) && openQuestions().length > 0;
  const labels = {
    // Scoping runs while the agent asks; its questions wait in the scope block, and « Plan » ends it.
    scoping: asking ? "scoping · questions waiting for you"
           : planPending() ? `scoping ended · the agent is writing the ${state.workflow === "view-branch" ? "model" : "plan"}`
           : "scoping the question",
    planning: "drafting the plan",
    ...(approval ? { [phase]: approvalPending() ? approval.sent : approval.ready } : {}),
    "awaiting-answer": openQuestions().length ? QUESTION_LABELS.ready : QUESTION_LABELS.sent,
    writing: section ? `writing §${numberOf(section)} ${titleOf(section)}` : "writing",
    audit: "vocabulary audit",
    revising: "revising",
  };
  const active = (phase === "scoping" && !asking) || ["planning", "writing", "audit", "revising"].includes(phase) ||
                 (approval && approvalPending()) || (phase === "awaiting-answer" && !asking);
  const p = $("#phase");
  p.hidden = !labels[phase];
  p.className = `phase ${active ? "active" : ""} ${(approval && !approvalPending()) || asking ? "ask" : ""}`;
  p.textContent = [labels[phase], message].filter(Boolean).join(" · ");

  $("#approve").hidden = docButton.hidden = prButton.hidden = true;
  if (!approval) return;
  const btn = buttonOf(approval);
  btn.hidden = approvalPending();
  const n = drafts.filter(ready).length;
  btn.textContent = n ? `${approval.label} + send ${n} comment${n > 1 ? "s" : ""}` : approval.label;
}

for (const b of [$("#approve"), docButton, prButton]) b.addEventListener("click", () => {
  const approval = APPROVALS[state.status.phase];
  if (approval) send(approval.action);
});

function renderPlan() {
  const { plan } = state;
  renderScope();
  const rev = $("#revision");
  if (plan.revision) {
    rev.hidden = false;
    rev.replaceChildren(
      el("span", { class: planChanged ? "badge flag" : "badge", text: planChanged ? "revised" : "last revision" }),
      " ", plan.revision,
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

function renderChanges() {
  const list = state.changes || [];
  $("#changes-head").hidden = !list.length;
  $("#changes").replaceChildren(...list.map((d) => {
    const item = el("li", { class: "change" },
      el("div", {}, el("span", { class: "num", text: d.id }), " ", d.change),
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

function renderDoc() {
  const doc = $("#doc");
  const sections = allSections();
  if (!sections.length) {
    doc.replaceChildren(el("p", { class: "dim empty", text: "Waiting for the plan…" }));
    $("#refactor").replaceChildren();
    return;
  }
  doc.replaceChildren(...sections.filter((s) => tabOf(s.id) === "doc").map((s) => sectionBlock(s)), docButton);
  $("#refactor").replaceChildren(...refactorTab(sections.filter((s) => tabOf(s.id) === "refactor")), prButton);
  for (const view of docViews()) {
    typesetMath(view);
    linkCitations(view);
    renderMermaid(view);
    annotateAudit(view);
    annotateLexicon(view);
  }
  applyHighlights();
  renderThreadChips();
  positionPopover();
}

/* A bare block leaves out the number and the title (the description of an item: its
   item entry shows both) and keeps everything else. */
function sectionBlock(s, { bare = false } = {}) {
  const body = el("div", { class: "body" });
  const written = s.id in state.sections;
  if (written) body.innerHTML = state.sections[s.id].html;
  else if (writingId() === s.id) body.append(el("p", { class: "writing-line", text: "writing" }));
  const cls = ["sec", written ? "" : "unwritten", isUpdated(s.id) ? "updated" : "", bare ? "bare" : ""].join(" ");
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
    body);
}

/* ---------------- the refactor tab ----------------
   A refactor section that carries item fields ("item": {files, verdict, batch?,
   implements, note, relations}) is an item: one unit of the diff, a file or files doing
   one job, judged against the model. The items are drawn as the review table: one item
   entry per item (its title and files, its verdict, its batch when any item has one, the
   concepts it implements, a note), the items that need action first. Clicking an entry opens its description underneath, which is
   the section's own block, so comments, threads, highlights and annotations work there
   as in the explanation. Below the table, the structure view (see structureView). The
   other refactor sections, such as the applied changes, follow as plain sections. A
   review whose refactor sections carry no item fields is drawn as plain sections only. */

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
  const after = rest.map((s) => sectionBlock(s));
  after.forEach((b) => b.classList.add("rv-after")); // aligned on the table, see app.css
  return [reviewTable(items), structureView(items, findings), ...after].filter(Boolean);
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

function findQuote(sectionId, quote, prefix) {
  const body = document.querySelector(`#sec-${CSS.escape(sectionId)} .body`);
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
    .map((t) => [t, findQuote(t.section, t.quote, t.prefix)]).filter(([, r]) => r);
  if (!window.CSS || !CSS.highlights) return;
  const draftRanges = drafts.map((d) => findQuote(d.section, d.quote, d.prefix)).filter(Boolean);
  const sentRanges = state.comments.batches.flatMap((b) => b.comments)
    .filter((c) => c.status === "sent")
    .map((c) => findQuote(c.section, c.quote, c.prefix)).filter(Boolean);
  CSS.highlights.set("ev-draft", new Highlight(...draftRanges));
  CSS.highlights.set("ev-sent", new Highlight(...sentRanges));
  CSS.highlights.set("ev-thread", new Highlight(...threadRanges.map(([, r]) => r)));
  markUpdates();
}

/* ---------------- updates since the last batch ----------------
   An updated section carries the HTML of its highlight baseline: its text when the last
   batch was sent, or when the user last marked it read.
   Both versions are cut into words, the words are diffed, and the words the rewrite
   inserted are highlighted ("ev-updated"); every block (paragraph, list item, cell…)
   holding an insertion or a deletion gets a bar in the margin. « updated · ok » in the
   section heading marks the section as read. */

const BLOCKS = "p, li, td, th, pre, blockquote, h1, h2, h3, h4, h5, h6, dt, dd, .math.block, .mermaid";

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
        const atom = n.matches(".math") ? n.dataset.tex ?? n.textContent
                   : n.matches(".mermaid") ? n.dataset.src
                   : n.matches("pre > code.language-mermaid") ? n.textContent : null;
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

/* Which words of `b` are not in `a` (`inserted`), and which words of `b` follow a run
   of words of `a` that is gone (`deleted`). Longest common subsequence, after trimming
   the common head and tail; a middle too large to compare counts as rewritten. */
function diffWords(a, b) {
  let lo = 0;
  while (lo < a.length && lo < b.length && a[lo] === b[lo]) lo++;
  let ea = a.length, eb = b.length;
  while (ea > lo && eb > lo && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const n = ea - lo, m = eb - lo;
  const inserted = new Set(), deleted = new Set();
  if (n * m > 4e6) {
    for (let j = lo; j < eb; j++) inserted.add(j);
    if (n) deleted.add(Math.min(lo, b.length - 1));
    return { inserted, deleted };
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
    if (i < n && j < m && a[lo + i] === b[lo + j]) { i++; j++; }
    else if (j < m && (i === n || L[i * (m + 1) + j + 1] >= L[(i + 1) * (m + 1) + j])) inserted.add(lo + j++);
    else { deleted.add(Math.min(lo + j, b.length - 1)); i++; }
  }
  return { inserted, deleted };
}

function markUpdates() {
  document.querySelectorAll(".changed").forEach((n) => n.classList.remove("changed"));
  const ranges = [];
  for (const [id, sec] of Object.entries(state.sections)) {
    const body = sec.updated && document.querySelector(`#sec-${CSS.escape(id)} .body`);
    if (!body) continue;
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
        ranges.push(run.range);
      }
    });
  }
  if (window.CSS && CSS.highlights) CSS.highlights.set("ev-updated", new Highlight(...ranges));
}

async function markSeen(ids) {
  try {
    await postJSON(`/api/s/${SLUG}/seen`, { sections: Object.fromEntries(ids.map((id) => [id, state.sections[id].md])) });
  } catch (e) { toast(`Could not mark as read: ${e.message}`); return; }
  await load();
}

function revealQuote(c) {
  if (!c.section) return;
  if (c.quote.startsWith("plan · ")) { setTab("plan"); return; }
  setTab(tabOf(c.section));
  openItemOf(c.section);
  const r = findQuote(c.section, c.quote, c.prefix);
  if (r) {
    r.startContainer.parentElement.scrollIntoView({ block: "center", behavior: "smooth" });
    if (CSS.highlights) {
      CSS.highlights.set("ev-focus", new Highlight(r));
      setTimeout(() => CSS.highlights.delete("ev-focus"), 1500);
    }
  } else scrollToSection(c.section);
}

/* A section that is an item is reached through its item entry: the entry opens, and is
   what scrolls into view, with its description under it. */
function scrollToSection(id) {
  setTab(tabOf(id));
  const s = openItemOf(id) || document.getElementById(`sec-${id}`);
  if (s) s.scrollIntoView({ block: "start", behavior: "smooth" });
}

/* ---------------- selection -> composer ---------------- */

function currentSelection() {
  const sel = getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
  const sec = start.closest(".sec");
  if (!sec || !sec.closest("#doc, #refactor")) return null;
  const body = $(".body", sec);
  const quote = collapse(sel.toString());
  if (!quote) return null;
  const before = document.createRange();
  before.setStart(body, 0);
  before.setEnd(range.startContainer, range.startOffset);
  const prefix = collapse(before.toString()).slice(-32);
  return { section: sec.dataset.id, quote, prefix, rect: range.getBoundingClientRect() };
}

document.addEventListener("mouseup", (e) => {
  if (e.target.closest("#composer, #sel-actions, #thread-pop")) return;
  setTimeout(() => {
    const s = currentSelection();
    const btn = $("#sel-actions");
    if (!s) {
      btn.hidden = true;
      pendingSelection = null;
      const t = threadAt(e.clientX, e.clientY);
      if (t) openPopover(t.id);
      return;
    }
    pendingSelection = s;
    btn.hidden = false;
    btn.style.top = `${window.scrollY + s.rect.bottom + 6}px`;
    btn.style.left = `${Math.max(8, s.rect.left)}px`;
  }, 0);
});

$("#sel-actions").addEventListener("mousedown", (e) => e.preventDefault());
$("#sel-actions .comment").addEventListener("click", () => {
  if (pendingSelection) openComposer(pendingSelection);
});
$("#sel-actions .ask").addEventListener("click", () => {
  if (pendingSelection) openComposer(pendingSelection, "ask");
});

/* The composer writes either a draft comment ("comment") or the first message of a
   new side thread ("ask"). */
function openComposer(target, mode = "comment") {
  $("#sel-actions").hidden = true;
  const c = $("#composer");
  c.hidden = false;
  c._target = target;
  c._mode = mode;
  $(".composer-quote", c).textContent = target.quote
    ? `« ${target.quote.length > 160 ? target.quote.slice(0, 160) + "…" : target.quote} »`
    : target.section ? `whole section §${numberOf(target.section)} ${titleOf(target.section)}`
    : "general question, no passage";
  $(".add", c).textContent = mode === "ask" ? "Ask" : "Add";
  $("#no-parent").hidden = mode !== "ask" || threadsState.forkable;
  $("textarea", c).placeholder = mode === "ask"
    ? "Your question for a side thread  (⌘↵ to ask, Esc to cancel)"
    : "Your comment  (⌘↵ to add, Esc to cancel)";
  const rect = target.rect || document.getElementById(`sec-${target.section}`).getBoundingClientRect();
  c.style.top = `${window.scrollY + Math.min(rect.bottom + 6, innerHeight - 220)}px`;
  c.style.left = `${Math.min(Math.max(8, rect.left), innerWidth - 380)}px`;
  const ta = $("textarea", c);
  ta.value = "";
  ta.focus();
}

function closeComposer() { $("#composer").hidden = true; }

function submitComposer() {
  if ($("#composer")._mode === "ask") askThread();
  else addDraft();
}

function addDraft() {
  const c = $("#composer");
  const text = $("textarea", c).value.trim();
  if (!text) return;
  const { section, quote, prefix } = c._target;
  drafts.push({ id: crypto.randomUUID(), section, quote, prefix, text });
  saveJSON(DRAFTS_KEY, drafts);
  closeComposer();
  getSelection().removeAllRanges();
  renderReview();
  applyHighlights();
}

$("#composer .add").addEventListener("click", submitComposer);
$("#composer .cancel").addEventListener("click", closeComposer);
$("#composer textarea").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitComposer(); }
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
   A box has three exits: « Validate » sends the answer at once (a batch whose action is
   "answer"), « Skip » sends « no answer, use your default » the same way (its entry
   `{question, skipped: true}`), or the box stays open: no question blocks the agent.
   The header holds « Grill me » (a batch whose action is "grill"; « Stop grill » sends
   "stop-grill" while a grill runs) and, while scoping runs or a question is open,
   « Plan » (action "plan": scoping ends, the open questions count as skipped). These
   three take the draft comments with them, like the approvals. */

const openQuestions = () => (state ? state.questions || [] : []).filter((q) => q.status === "open");
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
  const button = el("button", { class: "btn primary q-answer", text: "Validate" });
  const choices = () => [...options.querySelectorAll("input:checked")].map((i) => i.value);
  const update = () => { button.disabled = !choices().length && !ta.value.trim(); };
  update();
  options.addEventListener("change", update);
  ta.addEventListener("input", update);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); button.click(); }
  });
  const exit = async (path, body, done) => {
    button.disabled = skip.disabled = true;
    try {
      await postJSON(`/api/s/${SLUG}/questions/${q.id}/${path}`, body);
    } catch (e) { toast(`${done} failed: ${e.message}`); skip.disabled = false; update(); return; }
    await load();
    sentToast(`${done} ${q.id}`);
  };
  button.addEventListener("click", () => { if (!button.disabled) exit("answer", { choices: choices(), text: ta.value }, "Answered"); });
  skip.addEventListener("click", () => { if (!skip.disabled) exit("skip", {}, "Skipped"); });
  const card = el("div", { class: "question", "data-question": q.id },
    el("div", { class: "q-text" }, el("span", { class: "num", text: q.id }), " ", q.text),
    q.options.length ? options : null,
    rec && !recOption ? el("div", { class: "q-suggested" }, suggested()) : null,
    ta,
    el("div", { class: "q-actions" }, skip, button));
  questionCards.set(q.id, card);
  return card;
}

// A « plan » batch sent since the status last moved, with no question asked after it:
// scoping is over, the agent is writing the plan (or the model).
function planPending() {
  const since = state.status.since || "";
  return !openQuestions().length && state.comments.batches.some((b) => b.action === "plan" && b.sent >= since);
}

function renderScope() {
  const questions = state.questions || [];
  const open = openQuestions();
  for (const id of questionCards.keys()) if (!open.some((q) => q.id === id)) questionCards.delete(id);
  const box = $("#scope-questions");
  const cardsNow = open.map(questionCard);
  // Re-attaching a box would blur its text field: only when the list changed.
  if (cardsNow.length !== box.children.length || cardsNow.some((c, i) => box.children[i] !== c)) box.replaceChildren(...cardsNow);

  const closed = questions.filter((q) => q.status !== "open");
  const folded = $("#scope-answered");
  folded.hidden = !closed.length;
  $("summary", folded).textContent = `answered (${closed.length})`;
  $("ol", folded).replaceChildren(...closed.map((q) => el("li", {},
    el("div", { class: "q-text" }, el("span", { class: "num", text: q.id }), " ", q.text),
    el("div", { class: `q-reply ${q.status === "skipped" ? "dim" : ""}`,
                text: answerText(q.status === "skipped" ? { skipped: true } : q.answer || {}) }))));
  $("#scope-empty").hidden = questions.length > 0 || state.status.phase === "scoping";

  const grill = $("#grill");
  grill.textContent = state.grilling ? "Stop grill" : "Grill me";
  grill.title = state.grilling ? "Stop the interview" : "The agent asks about every open decision, each with its suggestion, until none is left";
  const plan = $("#scope-plan");
  plan.hidden = !(state.status.phase === "scoping" || open.length) || planPending();
  plan.title = "Enough questions: the open ones count as skipped, and the agent writes the plan";
}

$("#grill").addEventListener("click", (e) => send(state.grilling ? "stop-grill" : "grill", e.currentTarget));
$("#scope-plan").addEventListener("click", (e) => send("plan", e.currentTarget));

/* The review pane keeps one line for the open agent questions: it opens the Plan tab
   at the scope block. */
function renderWaiting() {
  const n = openQuestions().length;
  const line = $("#questions-waiting");
  line.hidden = !n;
  line.textContent = `${n} question${n > 1 ? "s" : ""} waiting →`;
}

$("#questions-waiting").addEventListener("click", () => {
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

function quoteLine(c) {
  const where = c.section ? `§${numberOf(c.section)}` : "·";
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
  $("#drafts").replaceChildren(...drafts.map((d) => {
    const ta = el("textarea", { class: "c-text", rows: "2",
                                placeholder: d.thread ? "What should change, after this thread? (optional)" : "" });
    ta.value = d.text;
    ta.addEventListener("input", () => { d.text = ta.value; saveJSON(DRAFTS_KEY, drafts); updateSend(); });
    return el("div", { class: "comment draft" },
      quoteLine(d), ta,
      el("button", { class: "c-del", text: "×", title: "Delete",
                     onclick: () => { drafts = drafts.filter((x) => x !== d); saveJSON(DRAFTS_KEY, drafts); renderReview(); applyHighlights(); renderPopover(); } }));
  }));
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
  const pane = $(".review");
  if (reviewAtEnd) pane.scrollTop = pane.scrollHeight;
}

/* An answered agent question in the history: its text, the answer (« skipped » for a
   skipped one), the agent's reply. */
const answerText = (a) => (a.skipped ? "skipped" : [(a.choices || []).join(", "), a.text].filter(Boolean).join(" — "));

function answeredQuestion(a, b) {
  const q = (state.questions || []).find((x) => x.id === a.question) || { id: a.question, text: "" };
  return el("div", { class: "question answered" },
    el("div", { class: "q-head" }, "Question from the agent ", el("span", { class: "dim", text: q.id })),
    q.text ? el("div", { class: "q-text", text: q.text }) : null,
    el("div", { class: `q-reply ${a.skipped ? "dim" : ""}`, text: answerText(a) }),
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

$("#note").value = loadJSON(NOTE_KEY, "");
$("#note").addEventListener("input", () => { saveJSON(NOTE_KEY, $("#note").value); updateSend(); });
$("#note").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
});
$("#send").addEventListener("click", () => send());

/* A batch from « Send », an approval button, or a scope block button (`button`). */
const SCOPE_TOASTS = { plan: "Scoping ended", grill: "Grill started", "stop-grill": "Grill stopped" };

async function send(action = "", button = null) {
  const approval = Object.values(APPROVALS).find((a) => a.action === action);
  const btn = button || (approval ? buttonOf(approval) : $("#send"));
  if (btn.disabled) return;
  btn.disabled = true;
  const r = await fetch(`/api/s/${SLUG}/batch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      action,
      note: $("#note").value,
      comments: drafts.map(({ section, quote, prefix, text, thread }) => ({ section, quote, prefix, text, thread })),
    }),
  });
  btn.disabled = false;
  if (!r.ok) { toast(`Send failed: ${(await r.json()).detail}`); updateSend(); return; }
  const b = await r.json();
  drafts = [];
  saveJSON(DRAFTS_KEY, drafts);
  $("#note").value = "";
  saveJSON(NOTE_KEY, "");
  await load();
  sentToast(approval ? approval.toast : SCOPE_TOASTS[action] || `Sent ${b.id} to the session`);
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

setReviewWidth(loadJSON(WIDTH_KEY, null));
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
addEventListener("resize", () => setReviewWidth(loadJSON(WIDTH_KEY, null)));

/* ---------------- side threads ----------------
   A thread opens in a popover on its passage. One is shown at a time; a click anywhere
   else closes it, and a click on the passage (highlighted) opens it again. A thread with
   no passage to sit on (a whole-section thread, a general one, or one whose passage was
   rewritten) gets a chip instead: in its section's heading, or in the top bar for a
   general one. The popover follows its anchor when the view scrolls, and hides while the
   anchor is out of sight.

   A thread's card is built once and then patched in place (head, messages, footer
   state), so a streaming reply never takes the focus or the text of its reply box. */

async function loadThreads() {
  const r = await fetch(`/api/s/${SLUG}/threads`);
  if (!r.ok) return;
  threadsState = await r.json();
  for (const id of cards.keys()) if (!threadsState.threads.some((t) => t.id === id)) cards.delete(id);
  if (state) { applyHighlights(); renderThreadChips(); }
  renderPopover();
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
  const { section, quote, prefix } = c._target;
  try {
    const t = await postJSON(`/api/s/${SLUG}/threads`, { section, quote, prefix, text });
    closeComposer();
    getSelection().removeAllRanges();
    popThread = t.id;
    await loadThreads();
  } catch (e) { toast(`Could not start the thread: ${e.message}`); }
}

$("#new-thread").addEventListener("click", (e) =>
  openComposer({ section: "", quote: "", prefix: "", rect: e.target.getBoundingClientRect() }, "ask"));

const threadOf = (id) => threadsState.threads.find((t) => t.id === id);
const sentThreads = () => new Set((state ? state.comments.batches : []).flatMap((b) => b.comments).map((c) => c.thread).filter(Boolean));

/* The threads without a passage on the page, as chips. */
function renderThreadChips() {
  const placed = new Set(threadRanges.map(([t]) => t.id));
  const chip = (t) => el("button", {
    class: `t-chip ${t.state === "running" ? "running" : t.state === "error" ? "error" : ""}`,
    "data-thread": t.id, text: t.id, title: (t.messages[0] || {}).text || "",
    onclick: (e) => { e.stopPropagation(); popThread === t.id ? closePopover() : openPopover(t.id); },
  });
  document.querySelectorAll(".t-chips[data-section]").forEach((box) =>
    box.replaceChildren(...threadsState.threads
      .filter((t) => t.section === box.dataset.section && !placed.has(t.id)).map(chip)));
  $("#general-threads").replaceChildren(...threadsState.threads.filter((t) => !t.section).map(chip));
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
  const chip = document.querySelector(`.t-chip[data-thread="${CSS.escape(id)}"]`);
  return chip ? chip.getBoundingClientRect() : null;
}

function openPopover(id) {
  const t = threadOf(id);
  if (!t) return;
  if (t.section && !t.quote.startsWith("plan · ")) {
    if (tab !== tabOf(t.section)) setTab(tabOf(t.section));
    openItemOf(t.section);
  }
  popThread = id;
  renderPopover();
}

function closePopover() {
  popThread = null;
  $("#thread-pop").hidden = true;
}

function renderPopover() {
  const pop = $("#thread-pop");
  const t = popThread && threadOf(popThread);
  if (!t) { closePopover(); return; }
  const card = threadCard(t);
  patchCard(t, card);
  if (pop.firstChild !== card.root) pop.replaceChildren(card.root); // re-attaching would blur the reply box
  pop.hidden = false;
  positionPopover();
}

function positionPopover() {
  const pop = $("#thread-pop");
  if (!popThread || pop.hidden) return;
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
  const ta = el("textarea", { class: "c-text", rows: "2", placeholder: "Reply  (⌘↵ to send, Esc to close)" });
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
  };
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); replyThread(t.id); }
  });
  card.foot = el("div", { class: "t-foot" }, ta, el("div", { class: "t-actions" }, card.del, card.batch, card.stop, card.reply));
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
      : t.state === "error" ? el("span", { class: "badge flag", text: "error" }) : null),
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
  drafts = drafts.filter((d) => d.thread !== tid);
  saveJSON(DRAFTS_KEY, drafts);
  closePopover();
  renderReview();
  await loadThreads();
}

/* The conclusion of a thread reaches the main session as an ordinary comment, anchored
   where the thread was and carrying its id, so the session can read the thread. Its
   text is optional: without one, the thread's conclusion is the comment. */
function threadToBatch(tid) {
  const t = threadOf(tid);
  drafts.push({ id: crypto.randomUUID(), section: t.section, quote: t.quote, prefix: t.prefix, text: "", thread: tid });
  saveJSON(DRAFTS_KEY, drafts);
  renderReview();
  applyHighlights();
  renderPopover();
}

/* ---------------- export, tooltips ---------------- */

$("#export").addEventListener("click", async () => {
  const r = await fetch(`/api/s/${SLUG}/export`, { method: "POST" });
  const body = await r.json();
  toast(r.ok ? `Exported to explanations/${body.name}` : `Export failed: ${body.detail}`, 5000);
});

document.addEventListener("mouseover", (e) => {
  const t = e.target.closest("[data-tip], [data-term]");
  const tip = $("#tip");
  if (!t) { tip.hidden = true; return; }
  if (t.dataset.term !== undefined) {
    const entry = state.plan.lexicon[Number(t.dataset.term)];
    tip.replaceChildren(el("div", { class: "tip-term", text: entry.term }));
    const body = el("div", { class: "tip-body" });
    body.innerHTML = entry.tip_html;
    tip.append(body);
    typesetMath(tip);
  } else tip.textContent = t.dataset.tip;
  tip.hidden = false;
  const r = t.getBoundingClientRect();
  tip.style.top = `${window.scrollY + r.bottom + 4}px`;
  tip.style.left = `${Math.min(r.left, innerWidth - 360)}px`;
});

// ?static skips the live stream (headless rendering never finishes while it is open).
load().then(loadThreads).then(() => { if (!new URLSearchParams(location.search).has("static")) connect(); });
