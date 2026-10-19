/* view-concept — the published page's script: underlines the lexicon terms and shows
   their tip on hover, typesets the maths, draws the Mermaid charts and talks to the
   section frames.

   wrapTerm, annotateLexicon, typesetMath, renderMermaid and the tooltip handler mirror
   their namesakes in app.js (the session page): change them together. They differ only
   where the published page does: the lexicon is the JSON in #lexicon (each entry's term,
   home section and tip_html), every chart is in sight (no hidden tab), and a chart is
   redrawn when the reader's system switches between light and dark. */

"use strict";

const LEXICON = JSON.parse(document.getElementById("lexicon").textContent);

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(c);
  return n;
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
  const blocks = [...root.querySelectorAll("pre > code.language-mermaid")];
  if (!blocks.length) return;
  try {
    mermaidLib = mermaidLib || (await import("https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs")).default;
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    mermaidLib.initialize({ startOnLoad: false, theme: dark ? "dark" : "default" });
    const nodes = blocks.map((code) => {
      const div = el("div", { class: "mermaid", "data-src": code.textContent, text: code.textContent });
      code.parentElement.replaceWith(div);
      return div;
    });
    await mermaidLib.run({ nodes });
  } catch (e) { /* offline: the source stays as a code block */ }
}

/* A chart is drawn in the colours of the theme it was drawn under: when the system
   switches, put its source back as a code block and draw it again. */
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  document.querySelectorAll(".mermaid[data-src]").forEach((div) =>
    div.replaceWith(el("pre", {}, el("code", { class: "language-mermaid", text: div.dataset.src }))));
  renderMermaid(document);
});

const SKIP = "code, pre, .katex, .mermaid, .term, h2";

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

/* Terms carry the index of their lexicon entry; the tooltip renders the entry's
   tip_html (the developed `tip`, else the one-line definition). In its home section
   the first occurrence of a term is marked as its definition. */
function annotateLexicon(doc) {
  LEXICON.forEach((t, i) => {
    const home = doc.querySelector(`#sec-${CSS.escape(t.section || "")} .body`);
    if (home) wrapTerm(home, t.term, () => el("span", { class: "term def", "data-term": i }), { first: true });
    doc.querySelectorAll(".sec .body").forEach((body) =>
      wrapTerm(body, t.term, () => el("span", { class: "term", "data-term": i })));
  });
}

/* The tip of lexicon entry `i` under the rectangle `r` (in the viewport). */
function showTip(i, r) {
  const entry = LEXICON[i];
  const tip = document.getElementById("tip");
  tip.replaceChildren(el("div", { class: "tip-term", text: entry.term }));
  const body = el("div", { class: "tip-body" });
  body.innerHTML = entry.tip_html;
  tip.append(body);
  typesetMath(tip);
  tip.hidden = false;
  tip.style.top = `${window.scrollY + r.bottom + 4}px`;
  tip.style.left = `${window.scrollX + Math.max(8, Math.min(r.left, innerWidth - tip.offsetWidth - 8))}px`;
}

/* With a mouse, the tip shows while the pointer rests on the term. Under touch controls
   (the device's main pointer cannot hover, as app.js reads it) a tap on the term shows
   it, and a tap elsewhere or a scroll hides it. */
const TOUCH = matchMedia("(hover: none)");
const isTouch = () => TOUCH.matches;
function tipAt(e) {
  const t = e.target.closest && e.target.closest("[data-term]");
  if (!t) { document.getElementById("tip").hidden = true; return; }
  showTip(Number(t.dataset.term), t.getBoundingClientRect());
}
document.addEventListener("mouseover", (e) => { if (!isTouch()) tipAt(e); });
// A tap inside the tip leaves it, as in app.js.
document.addEventListener("click", (e) => { if (isTouch() && !e.target.closest("#tip")) tipAt(e); });
addEventListener("scroll", () => { if (isTouch()) document.getElementById("tip").hidden = true; }, { passive: true });

/* Section frames (an HTML section, see frame.py): each takes the height its content posts,
   and is told the page's theme at load and whenever it changes. The terms message gives
   it the lexicon terms to underline (the term its section is the home of, then every
   term), each keyed by its lexicon index; the term hover message it posts back shows that
   term's tip under the word. Mirrors the section frames of app.js, without the audit
   entries, the anchors and the changes. */
function postTheme(f) {
  if (f.contentWindow) f.contentWindow.postMessage({ viewConcept: "theme", theme: document.documentElement.dataset.theme }, "*");
}
function postTerms(f) {
  if (!f.contentWindow) return;
  const terms = [];
  LEXICON.forEach((t, i) => {
    if (t.section && t.section === f.dataset.section) terms.push({ term: t.term, kind: "def", key: { term: i } });
    terms.push({ term: t.term, kind: "term", key: { term: i } });
  });
  f.contentWindow.postMessage({ viewConcept: "terms", terms }, "*");
}
function frameTermHover(f, d) {
  const i = d.key && d.key.term;
  if (!d.rect || !Number.isInteger(i) || !LEXICON[i]) { document.getElementById("tip").hidden = true; return; }
  const b = f.getBoundingClientRect();
  const x = b.left + f.clientLeft, y = b.top + f.clientTop;
  showTip(i, { left: x + d.rect.left, bottom: y + d.rect.bottom });
}
window.addEventListener("message", (e) => {
  const d = e.data;
  if (!d) return;
  const f = [...document.querySelectorAll("iframe.frame")].find((n) => n.contentWindow === e.source);
  if (!f) return;
  if (d.viewConcept === "height") f.style.height = `${d.height}px`;
  else if (d.viewConcept === "term-hover") frameTermHover(f, d);
});
document.querySelectorAll("iframe.frame").forEach((f) => {
  f.addEventListener("load", () => { postTheme(f); postTerms(f); });
  postTheme(f);
  postTerms(f);
});
new MutationObserver(() => document.querySelectorAll("iframe.frame").forEach(postTheme))
  .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

// KaTeX loads deferred: it is there once the document is parsed.
document.addEventListener("DOMContentLoaded", () => {
  const doc = document.querySelector(".doc");
  typesetMath(doc);
  renderMermaid(doc);
  annotateLexicon(doc);
});
