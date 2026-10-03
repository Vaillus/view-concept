/* view-concept — the published page's script: underlines the lexicon terms and shows
   their tip on hover, typesets the maths and draws the Mermaid charts.

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

/* A tap on a phone fires mouseover too, so the tip shows there as well. */
document.addEventListener("mouseover", (e) => {
  const t = e.target.closest("[data-term]");
  const tip = document.getElementById("tip");
  if (!t) { tip.hidden = true; return; }
  const entry = LEXICON[Number(t.dataset.term)];
  tip.replaceChildren(el("div", { class: "tip-term", text: entry.term }));
  const body = el("div", { class: "tip-body" });
  body.innerHTML = entry.tip_html;
  tip.append(body);
  typesetMath(tip);
  tip.hidden = false;
  const r = t.getBoundingClientRect();
  tip.style.top = `${window.scrollY + r.bottom + 4}px`;
  tip.style.left = `${window.scrollX + Math.max(8, Math.min(r.left, innerWidth - tip.offsetWidth - 8))}px`;
});

// KaTeX loads deferred: it is there once the document is parsed.
document.addEventListener("DOMContentLoaded", () => {
  const doc = document.querySelector(".doc");
  typesetMath(doc);
  renderMermaid(doc);
  annotateLexicon(doc);
});
