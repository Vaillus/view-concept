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

   Text a script paints into a <canvas> is pixels, not text: it cannot be selected nor
   highlighted. */
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
  function collapse(s) { return s.replace(/\s+/g, " ").trim(); }

  // The section's text, whitespace collapsed and its scripts and styles left out, with
  // the DOM position of every character.
  function textIndex() {
    var text = "", pos = [], space = true;
    if (!document.body) return { text: text, pos: pos };
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        for (var p = n.parentElement; p; p = p.parentElement) if (HIDDEN[p.tagName]) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    while (walker.nextNode()) {
      var n = walker.currentNode;
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
    var p = collapse(prefix || "");
    var at = p ? index.text.indexOf(p + q) : -1;
    at = at >= 0 ? at + p.length : index.text.indexOf(q);
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
  addEventListener("mouseup", function () {
    setTimeout(function () {
      var s = selection();
      if (!s && !selected) return;
      selected = !!s;
      post(s ? { viewConcept: "selection", quote: s.quote, prefix: s.prefix, rect: s.rect }
             : { viewConcept: "selection", quote: "" });
    }, 0);
  });

  /* ---- the anchors and the reveal ---- */
  var KINDS = ["draft", "sent", "thread", "focus"];
  var anchors = [];
  var focus = null; // { quote, prefix } of the passage being revealed
  var marks = document.createElement("style");
  marks.textContent =
    "::highlight(ev-draft) { background-color: var(--flagbg); }\n" +
    "::highlight(ev-sent) { background-color: var(--accentbg); }\n" +
    "::highlight(ev-thread) { background-color: var(--altbg); }\n" +
    "::highlight(ev-focus) { background-color: var(--accent); color: var(--on-accent); }\n";
  (document.head || root).appendChild(marks);

  function highlight() {
    if (!window.CSS || !CSS.highlights) return;
    var index = textIndex(), ranges = { draft: [], sent: [], thread: [], focus: [] };
    anchors.forEach(function (a) {
      var r = ranges[a.kind] && findQuote(index, a.quote, a.prefix);
      if (r) ranges[a.kind].push(r);
    });
    var f = focus && findQuote(index, focus.quote, focus.prefix);
    if (f) ranges.focus.push(f);
    KINDS.forEach(function (k) {
      CSS.highlights.set("ev-" + k, new (Function.prototype.bind.apply(Highlight, [null].concat(ranges[k])))());
    });
  }

  // A script that redraws the section's text drops the ranges with the old nodes: find
  // the passages again once the change is done.
  var pending = false;
  function rehighlight() {
    if (pending || (!anchors.length && !focus)) return;
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

  addEventListener("message", function (e) {
    var d = e.data;
    if (e.source !== parent || !d) return;
    if (d.viewConcept === "theme" && d.theme) root.setAttribute("data-theme", d.theme);
    else if (d.viewConcept === "anchors" && Array.isArray(d.anchors)) { anchors = d.anchors; highlight(); }
    else if (d.viewConcept === "reveal") reveal(d.quote, d.prefix);
  });
})();
