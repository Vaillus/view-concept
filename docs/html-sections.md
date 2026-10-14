# HTML sections: the section frame

For whoever changes the code. What a user sees of an HTML section is in [`reference.md`](reference.md#html-sections).

## Why a frame

An HTML section is code written as for an artifact: its own styles and scripts. Options considered:

| Option | Problem |
|---|---|
| Paste it into the page, scripts dropped | its styles restyle the page; no behaviour |
| Paste it in, scripts run | its scripts and the page's share one document and break each other |
| A shadow root | walls off styles, not scripts; artifact code reaching `document` hits the page |
| One frame for the whole explanation | sections still share one document; every section pays the frame's costs |
| **One frame per HTML section** | the page loses direct access, so it talks to the frame by messages |

The frame pays once, in `frame.js`. The other options pay in every section, through a rule no check can enforce on scripts.

Two choices keep the frame from touching the section's own elements:

- **Terms are underlined with CSS highlights, never wrapped in a `<span>`**, so a script finds its text as it wrote it. A highlight cannot set font weight, so a term in its home section is not bold inside a frame.
- **Changed words come from the file, not the live frame.** The page compares the file's visible text (outside `<script>` and `<style>`) with the baseline, so a script redrawing its own text is never counted as a change.

## The frame head

`frame.py` `inject()` writes the frame head at the start of the section's `<head>`: one stylesheet, `tokens_css()`, then `frame.js`. The stylesheet is, in order, the theme palettes (`themes.css`), the `:root` block of `terminal.css` that binds the semantic tokens onto them (not the skin's own styles), the prose width (`_PROSE_CSS`), and `static/frame.css`, the base style and the component kit. The page, the published page and the vault export all serve this one stylesheet, so a section looks the same in each.

The base style is a default, not an override: it comes before the section's styles, and every selector of `frame.css` is wrapped in `:where()`, which has zero specificity, so any rule the section writes wins over it, property by property. The one exception is `.tab-panel[hidden] { display: none !important }`, so a section's own `display` on a panel never shows a hidden one. `tests/test_frame.py` checks both. A change to `frame.css` reaches every existing HTML section the next time it is drawn, sections written before the change included: its table rules apply to every `<table>`, not only to tables that carry a kit class.

## The kit's tabs

The tabs are a contract between three places: the classes `frame.css` styles, the markup the visual rule of each skill tells the writer to use (`skills/view-branch/SKILL.md`, `skills/view-branch/roles/writer.md`, `skills/view-refactor/SKILL.md`, `skills/view-concept/SKILL.md`), and what `frame.js` reads and sets. Change them together.

| Element | Markup | `frame.js` |
|---|---|---|
| tab set | `.tabs` | its direct children: the first `.tab-row`, and every `.tab-panel` |
| tab row | `.tab-row`, a direct child of `.tabs` | its direct `.tab` children are the buttons |
| tab | `.tab` button in the row | sets `aria-selected` to `"true"` on the selected one, `"false"` on the others |
| panel | `.tab-panel`, a direct child of `.tabs` | the n-th panel belongs to the n-th tab; sets `hidden` on every panel but the selected one |

At load, `initTabs()` selects in each `.tabs` the first tab whose `aria-selected` is `"true"`, or the first tab. A click on a `.tab` selects it (`selectTab()`).

A **holder** is an element that hides a passage while it is closed: a closed `<details>` (the passage outside its `<summary>`) or a hidden `.tab-panel`. `textIndex()` skips only script and style text, so a passage in a holder is found, but it has no box on screen: its highlights are not seen and its position measures as zeros. So `frame.js` opens the holders around a passage (`openFrom()`, `openHolders()`: sets `open` on each `<details>`, selects the tab of each panel):

- before it measures a passage to answer `reveal`;
- the first time it finds the passage of a comment, a side thread or a change (`openOnce()`, from `highlight()`), and never again for that passage, so a tab the reader closes is not reopened by a later message or a redraw.

A term opens nothing. A tab row shows one panel at a time: when two of its panels hold a passage, only one of them shows at load.

## Frame messages

`postMessage` objects named by `viewConcept`. Frame side: `static/frame.js`. Page side: `static/app.js` (`reader.js` in the published page).

| Message | Direction | What it does |
|---|---|---|
| `height` | frame → page | sizes the iframe to its content |
| `theme` | page → frame | applies the page's theme |
| `selection` | frame → page | opens the comment / ask box on the selected passage |
| `anchors` | page → frame | highlights the passages comments and threads quote |
| `placed` | frame → page | answers `anchors`: the threads whose passage was found, so their heading chip hides |
| `reveal` | page → frame | flashes a comment's passage |
| `revealed` | frame → page | answers `reveal` with its position; the page scrolls there |
| `thread-click` | frame → page | a click on a thread's passage opens the thread |
| `changes` | page → frame | the passages added since the last read; the frame highlights one while the pointer is over a block holding its start or its end |
| `terms` | page → frame | underlines lexicon terms and audit words |
| `term-hover` | frame → page | the term under the pointer; the page shows its tip |

When a script rewrites the section's text, `frame.js` repaints every highlight from what it already holds. The page sends nothing.

## Where things live

- `frame.py`: injects the frame head (`tokens_css()`: theme tokens, prose width and `static/frame.css`; then `frame.js`) into the section's file, the sandbox flags, and the visible text that `check` and the agents' context read.
- `server.py`: serves the section and its media folder with a `Content-Security-Policy: sandbox` header, so they stay isolated even when opened in their own tab.
- `publish.py` and `store.py` (vault export): copy the file, its media and the frame's files. In Obsidian, `vault-section.js` handles `height` only.
