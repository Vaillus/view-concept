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
| `changes` | page → frame | highlights the words added since the last read |
| `terms` | page → frame | underlines lexicon terms and audit words |
| `term-hover` | frame → page | the term under the pointer; the page shows its tip |

When a script rewrites the section's text, `frame.js` repaints every highlight from what it already holds. The page sends nothing.

## Where things live

- `frame.py`: injects the frame's head (theme tokens and `frame.js`) into the section's file, the sandbox flags, and the visible text that `check` and the agents' context read.
- `server.py`: serves the section and its media folder with a `Content-Security-Policy: sandbox` header, so they stay isolated even when opened in their own tab.
- `publish.py` and `store.py` (vault export): copy the file, its media and the frame's files. In Obsidian, `vault-section.js` handles `height` only.
