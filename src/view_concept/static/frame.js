/* view-concept — the frame script: the page's own script, written at the start of every
   HTML section the page, the published page or the vault note draws (frame.py), after the
   theme tokens. The page cannot read the frame, nor the frame the page: the frame has an
   origin of its own, so they talk by frame messages, each an object whose `viewConcept`
   names it. The frame script is the frame's end of every one; the section's own scripts
   take no part.

   - The theme (page -> frame): the tokens define every theme, keyed by data-theme on
     <html>. The page posts its theme at load and at every change; until then (and where
     no page posts one, as in a vault note) the frame keeps the theme already set, or
     takes the page's default: Catppuccin Latte in light mode, Tokyo Night in dark mode.
   - The height (frame -> page): posted whenever the content's height changes, so the
     frame takes that height.
   - The selection (frame -> page): when the reader selects text in the section, the
     quoted text and the few characters before it (the anchor a passage of a Markdown
     section gets), with where the selection sits in the frame; an empty quote when the
     selection is gone. The page opens the same box to comment or to ask on it.
   - The anchors (page -> frame): the passages the page's drafts, sent comments and side
     threads quote in this section. Each is highlighted, and highlighted again when a
     script of the section redraws its text.
   - The reveal (page -> frame), answered by "revealed" (frame -> page): a passage to
     show. The frame highlights it for a moment and answers with where it sits, so the
     page scrolls to it; the frame takes the height of its content, so the scrolling is
     the page's.
   - The thread click (frame -> page): a click, with nothing selected, on a passage
     highlighted for a side thread gives the thread's id and where the passage sits, so
     the page opens that thread on it.
   - The changes (page -> frame): the passages an agent added since the last batch or
     « mark read ». The page finds them by comparing the section's visible text now and
     then; the frame highlights them as it highlights the anchors.
   - The terms (page -> frame): the lexicon terms, the one this section is the home of,
     and the words the vocabulary audit flags in it. The frame underlines each
     occurrence by painting a style over the word, as it paints the anchors: no element
     of the section is changed, so its scripts find their text as they wrote it.
   - The term hover (frame -> page): the underlined word the pointer rests on and where
     it sits, or nothing once the pointer leaves it, so the page shows that term's tip.

   Every highlight and underline is painted again when a script of the section redraws
   its text, from the anchors, changes and terms the frame already holds. Text a script
   paints into a <canvas> is pixels, not text: it cannot be selected, highlighted nor
   underlined. */
(function () {
  var root = document.documentElement;
  if (!root.hasAttribute("data-theme")) {
    var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
    root.setAttribute("data-theme", dark ? "tokyo-night" : "catppuccin-latte");
  }
  var framed = parent !== window;
  function post(message) { if (framed) parent.postMessage(message, "*"); }

  /* ---- the height ---- */
  var last = -1;
  function postHeight() {
    var height = Math.ceil(root.getBoundingClientRect().height);
    if (height === last) return;
    last = height;
    post({ viewConcept: "height", height: height });
  }
  if (window.ResizeObserver) new ResizeObserver(postHeight).observe(root);
  addEventListener("load", postHeight);

  /* ---- quotes <-> ranges, as the page finds them in a Markdown section ---- */
  var HIDDEN = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1 };
  // The elements whose text is not run on with the text around them (as app.js): a space
  // stands between two of them, so two paragraphs do not make one word.
  var BLOCKS = "address, article, aside, blockquote, dd, details, div, dl, dt, figcaption, figure, footer, " +
    "form, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, summary, table, td, th, tr, ul, " +
    "button, caption, label, option, text, tspan, br";
  function collapse(s) { return s.replace(/\s+/g, " ").trim(); }

  // The section's text, whitespace collapsed and its scripts and styles left out, with
  // the DOM position of every character (the space between two blocks takes the
  // position of the character after it).
  function textIndex() {
    var text = "", pos = [], space = true, block = null;
    if (!document.body) return { text: text, pos: pos };
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        for (var p = n.parentElement; p; p = p.parentElement) if (HIDDEN[p.tagName]) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    while (walker.nextNode()) {
      var n = walker.currentNode, b = n.parentElement.closest(BLOCKS);
      if (b !== block && !space && n.data.length) { text += " "; pos.push([n, 0]); space = true; }
      block = b;
      for (var i = 0; i < n.data.length; i++) {
        var ws = /\s/.test(n.data[i]);
        if (ws && space) continue;
        text += ws ? " " : n.data[i];
        pos.push([n, i]);
        space = ws;
      }
    }
    return { text: text, pos: pos };
  }

  function findQuote(index, quote, prefix) {
    var q = collapse(quote || "");
    if (!q) return null;
    // The prefix is collapsed, so a space between it and the quote is trimmed off it.
    var p = collapse(prefix || ""), at = -1;
    if (p) {
      at = index.text.indexOf(p + q);
      if (at >= 0) at += p.length;
      else if ((at = index.text.indexOf(p + " " + q)) >= 0) at += p.length + 1;
    }
    if (at < 0) at = index.text.indexOf(q);
    if (at < 0) return null;
    var s = index.pos[at], e = index.pos[at + q.length - 1];
    var r = document.createRange();
    r.setStart(s[0], s[1]);
    r.setEnd(e[0], e[1] + 1);
    return r;
  }

  /* ---- the selection ---- */
  var selected = false;
  function selection() {
    var sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return null;
    var range = sel.getRangeAt(0);
    var quote = collapse(sel.toString());
    if (!quote) return null;
    var index = textIndex(), k = 0;
    while (k < index.pos.length && range.comparePoint(index.pos[k][0], index.pos[k][1]) < 0) k++;
    var r = range.getBoundingClientRect();
    return { quote: quote, prefix: collapse(index.text.slice(0, k)).slice(-32),
             rect: { left: r.left, top: r.top, right: r.right, bottom: r.bottom } };
  }
  addEventListener("mouseup", function (e) {
    setTimeout(function () {
      var s = selection();
      if (s || selected) {
        selected = !!s;
        post(s ? { viewConcept: "selection", quote: s.quote, prefix: s.prefix, rect: s.rect }
               : { viewConcept: "selection", quote: "" });
      }
      if (!s) threadClick(e.clientX, e.clientY);
    }, 0);
  });

  /* ---- the anchors, the changes, the terms and the reveal ---- */
  var anchors = []; // { kind: draft | sent | thread, quote, prefix, thread? }
  var changes = []; // { quote, prefix }
  var terms = [];   // { term, kind: term | def | audit, key }
  var focus = null; // { quote, prefix } of the passage being revealed
  var threadRanges = [], termRanges = []; // [anchor, range], [term, range] as last painted
  var KINDS = ["draft", "sent", "thread", "focus", "updated", "term", "def", "audit"];
  var marks = document.createElement("style");
  marks.textContent =
    "::highlight(ev-draft) { background-color: var(--flagbg); }\n" +
    "::highlight(ev-sent) { background-color: var(--accentbg); }\n" +
    "::highlight(ev-thread) { background-color: var(--altbg); }\n" +
    "::highlight(ev-focus) { background-color: var(--accent); color: var(--on-accent); }\n" +
    "::highlight(ev-updated) { background-color: var(--okbg); text-decoration: underline 2px var(--ok); text-underline-offset: 3px; }\n" +
    "::highlight(ev-term) { text-decoration: underline dotted var(--line-strong); text-underline-offset: 3px; }\n" +
    "::highlight(ev-def) { text-decoration: underline solid var(--accent); text-underline-offset: 3px; }\n" +
    "::highlight(ev-audit) { text-decoration: underline wavy var(--warn); text-underline-offset: 3px; }\n";
  (document.head || root).appendChild(marks);

  // Letter-aware word boundaries, as the page uses: "état" does not match in "étatique".
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function termRe(term) {
    try { return new RegExp("(?<![\\p{L}\\p{N}])" + escapeRe(term) + "(?![\\p{L}\\p{N}])", "giu"); }
    catch (err) { return null; }
  }
  function rangeAt(index, start, end) {
    var s = index.pos[start], e = index.pos[end - 1];
    var r = document.createRange();
    r.setStart(s[0], s[1]);
    r.setEnd(e[0], e[1] + 1);
    return r;
  }

  // The underlines, in the page's order: the audit's first, then the home section's
  // first occurrence of its term, then every other occurrence; a word already
  // underlined is not underlined again.
  function underline(index) {
    var taken = [], out = [];
    var free = function (a, b) { return taken.every(function (t) { return b <= t[0] || a >= t[1]; }); };
    ["audit", "def", "term"].forEach(function (kind) {
      terms.forEach(function (t) {
        if (t.kind !== kind || !String(t.term || "").trim()) return;
        var re = termRe(String(t.term)), m;
        if (!re) return;
        while ((m = re.exec(index.text))) {
          var a = m.index, b = a + m[0].length;
          if (!m[0].length) { re.lastIndex++; continue; }
          if (!free(a, b)) continue;
          taken.push([a, b]);
          out.push([t, rangeAt(index, a, b)]);
          if (kind === "def") break;
        }
      });
    });
    return out;
  }

  function highlight() {
    if (!window.CSS || !CSS.highlights) return;
    var index = textIndex(), ranges = {};
    KINDS.forEach(function (k) { ranges[k] = []; });
    threadRanges = [];
    anchors.forEach(function (a) {
      var r = ranges[a.kind] && findQuote(index, a.quote, a.prefix);
      if (!r) return;
      ranges[a.kind].push(r);
      if (a.kind === "thread" && a.thread) threadRanges.push([a, r]);
    });
    changes.forEach(function (c) {
      var r = findQuote(index, c.quote, c.prefix);
      if (r) ranges.updated.push(r);
    });
    var f = focus && findQuote(index, focus.quote, focus.prefix);
    if (f) ranges.focus.push(f);
    termRanges = underline(index);
    termRanges.forEach(function (tr) { ranges[tr[0].kind].push(tr[1]); });
    KINDS.forEach(function (k) {
      CSS.highlights.set("ev-" + k, new (Function.prototype.bind.apply(Highlight, [null].concat(ranges[k])))());
    });
  }

  // A script that redraws the section's text drops the ranges with the old nodes: find
  // the passages and the terms again once the change is done.
  var pending = false;
  function rehighlight() {
    if (pending || (!anchors.length && !changes.length && !terms.length && !focus)) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; highlight(); });
  }
  new MutationObserver(rehighlight).observe(root, { childList: true, characterData: true, subtree: true });

  function reveal(quote, prefix) {
    var r = findQuote(textIndex(), quote, prefix);
    if (!r) { post({ viewConcept: "revealed", found: false }); return; }
    var b = r.getBoundingClientRect();
    post({ viewConcept: "revealed", found: true, top: b.top + scrollY, bottom: b.bottom + scrollY });
    focus = { quote: quote, prefix: prefix };
    highlight();
    setTimeout(function () { focus = null; highlight(); }, 1500);
  }

  function rectOf(r) { return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; }
  function hit(list, x, y) {
    for (var i = 0; i < list.length; i++) {
      var rects = list[i][1].getClientRects();
      for (var j = 0; j < rects.length; j++) {
        var b = rects[j];
        if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) return [list[i][0], b];
      }
    }
    return null;
  }

  /* ---- the thread click ---- */
  function threadClick(x, y) {
    var h = hit(threadRanges, x, y);
    if (h) post({ viewConcept: "thread-click", thread: h[0].thread, rect: rectOf(h[1]) });
  }

  /* ---- the term hover ---- */
  var hovered = null;
  function hover(t, rect) {
    if (t === hovered) return;
    hovered = t;
    post(t ? { viewConcept: "term-hover", key: t.key, rect: rectOf(rect) } : { viewConcept: "term-hover", key: null });
  }
  addEventListener("mousemove", function (e) {
    var h = hit(termRanges, e.clientX, e.clientY);
    hover(h && h[0], h && h[1]);
    // The passage of a thread is clickable: say so with the cursor.
    root.style.cursor = hit(threadRanges, e.clientX, e.clientY) ? "pointer" : "";
  });
  document.addEventListener("mouseleave", function () { hover(null); });
  addEventListener("scroll", function () { hover(null); });

  addEventListener("message", function (e) {
    var d = e.data;
    if (e.source !== parent || !d) return;
    if (d.viewConcept === "theme" && d.theme) root.setAttribute("data-theme", d.theme);
    else if (d.viewConcept === "anchors" && Array.isArray(d.anchors)) { anchors = d.anchors; highlight(); }
    else if (d.viewConcept === "changes" && Array.isArray(d.changes)) { changes = d.changes; highlight(); }
    else if (d.viewConcept === "terms" && Array.isArray(d.terms)) { terms = d.terms; hover(null); highlight(); }
    else if (d.viewConcept === "reveal") reveal(d.quote, d.prefix);
  });
})();
