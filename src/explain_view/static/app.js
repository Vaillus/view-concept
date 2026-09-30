/* explain-view — the session page.

   Two tabs share the main space, the plan (outline, decisions, lexicon) and the
   explanation (one block per outline section); the review pane (draft comments, then
   sent batches) stays on the right. The page never
   edits the explanation: Claude Code writes the files, the server streams "changed",
   the page re-fetches. The only thing the page writes is a batch of comments.

   A comment is anchored by (section id, quoted text, a few characters of prefix). The
   quote is searched again after every re-render, so an anchor survives edits elsewhere
   in the section and silently disappears when its passage is rewritten. */

"use strict";

const SLUG = decodeURIComponent(location.pathname.split("/").pop());
const DRAFTS_KEY = `explain-view:drafts:${SLUG}`;
const NOTE_KEY = `explain-view:note:${SLUG}`;

let state = null;        // last payload from /api/s/<slug>
let lastMd = null;       // section id -> markdown, to detect rewritten sections
const updated = new Set(); // sections rewritten since the user last acknowledged them
let planChanged = false;
let drafts = loadJSON(DRAFTS_KEY, []);
let pendingSelection = null;
let tab = null;          // "plan" | "doc"
let lastPhase = null;

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

/* ---------------- data ---------------- */

async function load() {
  const r = await fetch(`/api/s/${SLUG}`);
  if (!r.ok) {
    $("#doc").replaceChildren(el("p", { class: "error", text: `Could not load: ${(await r.json()).detail}` }));
    return;
  }
  const next = await r.json();
  const md = Object.fromEntries(Object.entries(next.sections).map(([k, v]) => [k, v.md]));
  if (lastMd) {
    // A first write is not an update: only a section that already had text is marked.
    for (const [k, v] of Object.entries(md)) if (k in lastMd && lastMd[k] !== v) updated.add(k);
    if (JSON.stringify(state.plan) !== JSON.stringify(next.plan)) planChanged = true;
  }
  lastMd = md;
  state = next;
  render();
}

function connect() {
  const es = new EventSource(`/api/s/${SLUG}/events`);
  const live = $("#live");
  es.addEventListener("hello", () => { live.textContent = "live"; live.className = "live on"; });
  es.addEventListener("changed", () => load());
  es.onerror = () => { live.textContent = "offline"; live.className = "live off"; };
}

/* ---------------- render ---------------- */

function outlineItems() {
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

function render() {
  const { plan } = state;
  document.title = `${plan.title} · explain-view`;
  $("#title").textContent = plan.title;
  renderStatus();
  followSession();
  renderPlan();
  renderDoc();
  renderReview();
}

/* ---------------- tabs ----------------
   The plan and the explanation share one space; one is shown at a time. The tab follows
   the session at the two moments that matter — the plan waiting for approval, the
   writing starting — and otherwise stays where the user put it. */

function setTab(name) {
  tab = name;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  $("#comment-btn").hidden = true;
}

function followSession() {
  const phase = state.status.phase;
  if (tab === null) setTab(Object.keys(state.sections).length && phase !== "awaiting-approval" ? "doc" : "plan");
  else if (phase !== lastPhase) {
    if (phase === "awaiting-approval") setTab("plan");
    if (phase === "writing") setTab("doc");
  }
  lastPhase = phase;
  const docTab = $('.tab[data-tab="doc"]');
  docTab.replaceChildren("explanation",
    updated.size ? el("span", { class: "badge flag", text: `${updated.size} updated` }) : null,
    phase === "writing" ? el("span", { class: "badge accent writing", text: "writing" }) : null);
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
document.addEventListener("keydown", (e) => {
  if (e.target.closest("textarea, input") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "1") setTab("plan");
  if (e.key === "2") setTab("doc");
});

/* ---------------- status + plan approval ---------------- */

const writingId = () => (state.status.phase === "writing" ? state.status.section : "");

/* The plan is approved from the page by a batch carrying action "approve-plan". Until
   Claude moves the status on, the page says the approval is on its way. */
function approvalPending() {
  const since = state.status.since || "";
  return state.comments.batches.some((b) => b.action === "approve-plan" && b.sent >= since);
}

function renderStatus() {
  const { phase, section, message } = state.status;
  const labels = {
    scoping: "scoping the question",
    planning: "drafting the plan",
    "awaiting-approval": approvalPending() ? "plan approved · Claude is starting" : "plan ready · waiting for your approval",
    writing: section ? `writing §${numberOf(section)} ${titleOf(section)}` : "writing",
    audit: "vocabulary audit",
    revising: "revising",
  };
  const active = ["scoping", "planning", "writing", "audit", "revising"].includes(phase) ||
                 (phase === "awaiting-approval" && approvalPending());
  const p = $("#phase");
  p.hidden = !labels[phase];
  p.className = `phase ${active ? "active" : ""} ${phase === "awaiting-approval" && !approvalPending() ? "ask" : ""}`;
  p.textContent = [labels[phase], message].filter(Boolean).join(" · ");

  const btn = $("#approve");
  btn.hidden = phase !== "awaiting-approval" || approvalPending();
  const n = drafts.filter((d) => d.text.trim()).length;
  btn.textContent = n ? `Approve plan + send ${n} comment${n > 1 ? "s" : ""}` : "Approve plan";
}

$("#approve").addEventListener("click", () => send("approve-plan"));

function renderPlan() {
  const { plan } = state;
  const rev = $("#revision");
  if (plan.revision) {
    rev.hidden = false;
    rev.replaceChildren(
      el("span", { class: planChanged ? "badge flag" : "badge", text: planChanged ? "revised" : "last revision" }),
      " ", plan.revision,
    );
    rev.onclick = () => { planChanged = false; renderPlan(); };
  } else rev.hidden = true;

  $("#outline").replaceChildren(...outlineItems().map((s) => {
    const written = s.id in state.sections;
    return el("li", { class: `${written ? "" : "pending"} ${updated.has(s.id) ? "updated" : ""}`,
                      onclick: () => scrollToSection(s.id) },
      el("button", { class: "o-comment", text: "+ comment", title: "Comment on this item of the plan",
                     onclick: (e) => {
                       e.stopPropagation();
                       openComposer({ section: s.id, quote: `plan · ${s.title}`, prefix: "", rect: e.target.getBoundingClientRect() });
                     } }),
      el("div", { class: "o-title" },
        el("span", { class: "num", text: numberOf(s.id) }), " ", s.title,
        s.kind === "question" ? el("span", { class: "badge alt", text: "Q" }) : null,
        writingId() === s.id ? el("span", { class: "badge accent writing", text: "writing" }) : null,
        updated.has(s.id) ? el("span", { class: "badge flag", text: "updated" }) : null),
      s.earns ? el("div", { class: "o-earns muted", text: s.earns }) : null);
  }));

  renderDecisions();

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

function renderDecisions() {
  const list = state.decisions || [];
  $("#decisions-head").hidden = !list.length;
  $("#decisions").replaceChildren(...list.map((d) => {
    const item = el("li", { class: "decision" },
      el("div", {}, el("span", { class: "num", text: d.id }), " ", d.decision),
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
  const items = outlineItems();
  if (!items.length) {
    doc.replaceChildren(el("p", { class: "dim empty", text: "Waiting for the plan…" }));
    return;
  }
  doc.replaceChildren(...items.map((s) => {
    const body = el("div", { class: "body" });
    const written = s.id in state.sections;
    if (written) body.innerHTML = state.sections[s.id].html;
    else if (writingId() === s.id) body.append(el("p", { class: "writing-line", text: "writing" }));
    const cls = ["sec", written ? "" : "unwritten", updated.has(s.id) ? "updated" : ""].join(" ");
    return el("section", { class: cls, id: `sec-${s.id}`, "data-id": s.id },
      el("h2", {},
        el("span", { class: "num", text: numberOf(s.id) }), " ", s.title,
        s.kind === "question" && s.from && s.from.length
          ? el("span", { class: "q-from dim", text: `from ${[].concat(s.from).join(", ")}` }) : null,
        updated.has(s.id)
          ? el("button", { class: "badge flag", text: "updated · ok", title: "Mark as read",
                           onclick: (e) => { e.stopPropagation(); updated.delete(s.id); render(); } })
          : null,
        el("button", { class: "sec-comment", text: "+ comment section", title: "Comment on the whole section",
                       onclick: () => openComposer({ section: s.id, quote: "", prefix: "" }) })),
      body);
  }));
  typesetMath(doc);
  linkCitations(doc);
  renderMermaid(doc);
  annotateAudit(doc);
  annotateLexicon(doc);
  applyHighlights();
}

function typesetMath(root) {
  if (!window.katex) return;
  root.querySelectorAll(".math").forEach((m) => {
    try {
      katex.render(m.textContent, m, { displayMode: m.classList.contains("block"), throwOnError: false });
    } catch (e) { /* leave the TeX source visible */ }
  });
}

let mermaidLib = null;
async function renderMermaid(root) {
  const blocks = root.querySelectorAll("pre > code.language-mermaid");
  if (!blocks.length) return;
  try {
    mermaidLib = mermaidLib || (await import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")).default;
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    mermaidLib.initialize({ startOnLoad: false, theme: dark ? "dark" : "default" });
    const nodes = [...blocks].map((code) => {
      const div = el("div", { class: "mermaid", text: code.textContent });
      code.parentElement.replaceWith(div);
      return div;
    });
    await mermaidLib.run({ nodes });
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

function annotateAudit(doc) {
  for (const a of state.audit || []) {
    const sec = doc.querySelector(`#sec-${CSS.escape(a.section || "")} .body`);
    if (!sec) continue;
    wrapTerm(sec, a.term || "", () => el("span", {
      class: "audit", "data-tip": `audit · ${a.issue || "flagged"}${a.note ? " — " + a.note : ""}`,
    }));
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
  if (!window.CSS || !CSS.highlights) return;
  const draftRanges = drafts.map((d) => findQuote(d.section, d.quote, d.prefix)).filter(Boolean);
  const sentRanges = state.comments.batches.flatMap((b) => b.comments)
    .filter((c) => c.status === "sent")
    .map((c) => findQuote(c.section, c.quote, c.prefix)).filter(Boolean);
  CSS.highlights.set("ev-draft", new Highlight(...draftRanges));
  CSS.highlights.set("ev-sent", new Highlight(...sentRanges));
}

function revealQuote(c) {
  if (c.quote.startsWith("plan · ")) { setTab("plan"); return; }
  setTab("doc");
  const r = findQuote(c.section, c.quote, c.prefix);
  if (r) {
    r.startContainer.parentElement.scrollIntoView({ block: "center", behavior: "smooth" });
    if (CSS.highlights) {
      CSS.highlights.set("ev-focus", new Highlight(r));
      setTimeout(() => CSS.highlights.delete("ev-focus"), 1500);
    }
  } else scrollToSection(c.section);
}

function scrollToSection(id) {
  setTab("doc");
  const s = document.getElementById(`sec-${id}`);
  if (s) s.scrollIntoView({ block: "start", behavior: "smooth" });
}

/* ---------------- selection -> composer ---------------- */

function currentSelection() {
  const sel = getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  const start = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
  const sec = start.closest(".sec");
  if (!sec || !$("#doc").contains(sec)) return null;
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
  if (e.target.closest("#composer, #comment-btn")) return;
  setTimeout(() => {
    const s = currentSelection();
    const btn = $("#comment-btn");
    if (!s) { btn.hidden = true; pendingSelection = null; return; }
    pendingSelection = s;
    btn.hidden = false;
    btn.style.top = `${window.scrollY + s.rect.bottom + 6}px`;
    btn.style.left = `${Math.max(8, s.rect.left)}px`;
  }, 0);
});

$("#comment-btn").addEventListener("mousedown", (e) => e.preventDefault());
$("#comment-btn").addEventListener("click", () => {
  if (pendingSelection) openComposer(pendingSelection);
});

function openComposer(target) {
  $("#comment-btn").hidden = true;
  const c = $("#composer");
  c.hidden = false;
  c._target = target;
  $(".composer-quote", c).textContent = target.quote
    ? `« ${target.quote.length > 160 ? target.quote.slice(0, 160) + "…" : target.quote} »`
    : `whole section §${numberOf(target.section)} ${titleOf(target.section)}`;
  const rect = target.rect || document.getElementById(`sec-${target.section}`).getBoundingClientRect();
  c.style.top = `${window.scrollY + Math.min(rect.bottom + 6, innerHeight - 220)}px`;
  c.style.left = `${Math.min(Math.max(8, rect.left), innerWidth - 380)}px`;
  const ta = $("textarea", c);
  ta.value = "";
  ta.focus();
}

function closeComposer() { $("#composer").hidden = true; }

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

$("#composer .add").addEventListener("click", addDraft);
$("#composer .cancel").addEventListener("click", closeComposer);
$("#composer textarea").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); addDraft(); }
  if (e.key === "Escape") closeComposer();
});

/* ---------------- review pane ---------------- */

function quoteLine(c) {
  const where = `§${numberOf(c.section)}`;
  const q = c.quote ? `« ${c.quote.length > 90 ? c.quote.slice(0, 90) + "…" : c.quote} »` : "whole section";
  return el("div", { class: "c-quote", onclick: () => revealQuote(c) },
    el("span", { class: "num", text: where }), " ", q);
}

function renderReview() {
  $("#draft-count").textContent = drafts.length ? `· ${drafts.length} draft${drafts.length > 1 ? "s" : ""}` : "";
  $("#drafts").replaceChildren(...drafts.map((d) => {
    const ta = el("textarea", { class: "c-text", rows: "2" });
    ta.value = d.text;
    ta.addEventListener("input", () => { d.text = ta.value; saveJSON(DRAFTS_KEY, drafts); });
    return el("div", { class: "comment draft" },
      quoteLine(d), ta,
      el("button", { class: "c-del", text: "×", title: "Delete",
                     onclick: () => { drafts = drafts.filter((x) => x !== d); saveJSON(DRAFTS_KEY, drafts); renderReview(); applyHighlights(); } }));
  }));
  updateSend();

  const batches = state ? [...state.comments.batches].reverse() : [];
  $("#sent").replaceChildren(...(batches.length ? batches.map((b) =>
    el("div", { class: "batch" },
      el("div", { class: "b-head dim", text: `${b.id} · ${new Date(b.sent).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` }),
      b.note ? el("div", { class: "b-note", text: b.note }) : null,
      ...b.comments.map((c) => el("div", { class: `comment ${c.status}` },
        quoteLine(c),
        el("div", { class: "c-text", text: c.text }),
        el("div", { class: "c-status" },
          el("span", { class: c.status === "resolved" ? "badge ok" : "badge", text: c.status === "resolved" ? "✓ resolved" : "waiting" }),
          c.reply ? el("span", { class: "c-reply", text: ` ${c.reply}` }) : null))))
  ) : [el("p", { class: "dim", text: "Nothing sent yet." })]));
}

function updateSend() {
  const note = $("#note").value.trim();
  const n = drafts.filter((d) => d.text.trim()).length;
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

async function send(action = "") {
  const btn = action ? $("#approve") : $("#send");
  if (btn.disabled) return;
  btn.disabled = true;
  const r = await fetch(`/api/s/${SLUG}/batch`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      action,
      note: $("#note").value,
      comments: drafts.map(({ section, quote, prefix, text }) => ({ section, quote, prefix, text })),
    }),
  });
  btn.disabled = false;
  if (!r.ok) { toast(`Send failed: ${(await r.json()).detail}`); updateSend(); return; }
  const b = await r.json();
  drafts = [];
  saveJSON(DRAFTS_KEY, drafts);
  $("#note").value = "";
  saveJSON(NOTE_KEY, "");
  toast(action ? "Plan approved" : `Sent ${b.id} to the session`);
  await load();
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
load().then(() => { if (!new URLSearchParams(location.search).has("static")) connect(); });
