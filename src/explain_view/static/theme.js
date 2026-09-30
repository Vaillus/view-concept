/* Pick the omarchy theme before the stylesheets apply, so the page never flashes the
   wrong palette. Loaded synchronously in <head> by every page. */
(function () {
  var t = null;
  try { t = localStorage.getItem("omarchy-theme"); } catch (e) {}
  if (!t) {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "tokyo-night" : "catppuccin-latte";
  }
  document.documentElement.setAttribute("data-theme", t);
})();
