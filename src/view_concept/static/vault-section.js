// Dataview view written by `view-concept export` as <slug>/section.js: draws one HTML
// section of the note in a section frame, a sandboxed iframe with an origin of its own, as the page does: its
// scripts run, its styles stay inside. Its head (as frame.inject) holds the theme tokens
// (frame.css) and frame.js: no page hands it a theme here, so it takes the page's default
// theme in the mode Obsidian is in. Relative addresses (its media folder) resolve
// against `root`, the vault path of this folder.
const { file, root } = input;
const read = (p) => app.vault.adapter.read(p);
const [html, tokens, js] = await Promise.all([read(file), read(`${root}/frame.css`), read(`${root}/frame.js`)]);
const theme = document.body.classList.contains("theme-dark") ? "tokyo-night" : "catppuccin-latte";
const base = app.vault.adapter.getResourcePath(root).replace(/\?.*$/, "") + "/";
const head = `<base href="${base}"><style>${tokens}</style>` +
  `<script>document.documentElement.setAttribute("data-theme", "${theme}");\n${js}<\/script>`;
const at = [/<head\b[^>]*>/i, /<html\b[^>]*>/i, /^\s*<!doctype\b[^>]*>/i].map((re) => html.match(re)).find(Boolean);
const end = at ? at.index + at[0].length : 0;
const frame = dv.container.createEl("iframe", {
  attr: { sandbox: "{SANDBOX}", allow: "fullscreen", srcdoc: html.slice(0, end) + head + html.slice(end) },
});
frame.style.cssText = "display: block; width: 100%; height: 150px; border: 1px solid var(--background-modifier-border);";
window.addEventListener("message", (e) => {
  if (e.source === frame.contentWindow && e.data && e.data.viewConcept === "height") frame.style.height = `${e.data.height}px`;
});
