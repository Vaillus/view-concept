/* view-concept — the head of a section frame: written at the start of every HTML section
   the page, the published page or the vault note draws (frame.py), after the theme
   tokens. The page cannot read the frame, nor the frame the page: the frame has an origin
   of its own, so they talk by messages.

   - The theme: the tokens define every theme, keyed by data-theme on <html>. The page
     posts its theme at load and at every change; until then (and where no page posts
     one, as in a vault note) the frame keeps the theme already set, or takes the page's
     default: Catppuccin Latte in light mode, Tokyo Night in dark mode.
   - The height: posted to the page whenever the content's height changes, so the frame
     takes that height. */
(function () {
  var root = document.documentElement;
  if (!root.hasAttribute("data-theme")) {
    var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
    root.setAttribute("data-theme", dark ? "tokyo-night" : "catppuccin-latte");
  }
  addEventListener("message", function (e) {
    var d = e.data;
    if (e.source === parent && d && d.viewConcept === "theme" && d.theme) root.setAttribute("data-theme", d.theme);
  });

  var last = -1;
  function post() {
    var height = Math.ceil(root.getBoundingClientRect().height);
    if (height === last) return;
    last = height;
    parent.postMessage({ viewConcept: "height", height: height }, "*");
  }
  if (window.ResizeObserver) new ResizeObserver(post).observe(root);
  addEventListener("load", post);
})();
