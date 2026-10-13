// Dataview view written by `view-concept export` as <slug>/section.js: draws one HTML
// section of the note in a section frame, a sandboxed iframe with an origin of its own, as the page does: its
// scripts run, its styles stay inside. The exported file already starts its head with
// the frame's head, two links to frame.css (the theme tokens) and frame.js; here they are
// replaced by the two files' text, so the frame does not load them through Obsidian's
// app:// address. Before them come a <base>, so relative addresses (its media folder)
// resolve against `root`, the vault path of this folder, and the theme: no page hands one
// here, so the section takes the page's default theme in the mode Obsidian is in, set
// before frame.js, which keeps a theme already set.
const { file, root } = input;
const read = (p) => app.vault.adapter.read(p);
const [html, tokens, js] = await Promise.all([read(file), read(`${root}/frame.css`), read(`${root}/frame.js`)]);
const theme = document.body.classList.contains("theme-dark") ? "tokyo-night" : "catppuccin-latte";
const base = app.vault.adapter.getResourcePath(root).replace(/\?.*$/, "") + "/";
const head = `<base href="${base}">` +
  `<script>document.documentElement.setAttribute("data-theme", "${theme}");<\/script>` +
  `<style>${tokens}</style><script>${js}<\/script>`;
const doc = html.split({HEAD}).join("");
const at = [/<head\b[^>]*>/i, /<html\b[^>]*>/i, /^\s*<!doctype\b[^>]*>/i].map((re) => doc.match(re)).find(Boolean);
const end = at ? at.index + at[0].length : 0;
const frame = dv.container.createEl("iframe", {
  attr: { sandbox: "{SANDBOX}", allow: "fullscreen", srcdoc: doc.slice(0, end) + head + doc.slice(end) },
});
frame.style.cssText = "display: block; width: 100%; height: 150px; border: 1px solid var(--background-modifier-border);";
window.addEventListener("message", (e) => {
  if (e.source === frame.contentWindow && e.data && e.data.viewConcept === "height") frame.style.height = `${e.data.height}px`;
});
