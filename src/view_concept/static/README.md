# static

The browser side of the page, the local web page that renders a session's files and sends your comments back to the agent: plain HTML, CSS and JavaScript, served by `server.py` with no build step.

```
session.html      # the session page: tabs, review pane, side threads
home.html         # the list of sessions
app.js            # the session page's script: rendering, comments, batches, the Doc tab
app.css           # the session page's rules, semantic colour tokens only
sidebar.js        # the sessions sidebar, grouped by project, on both pages
metrics.js        # the Metrics tab of a feature
frame.js          # the script written into every section frame (see below)
frame.css         # the base style and component kit of a section frame
published.html    # template of a published page
published.css     # the published page's reading rules
reader.js         # the published page's script; mirrors the term, maths, Mermaid and tooltip code of app.js
vault-section.js  # Obsidian Dataview view that draws an HTML section of an exported note
sw.js             # service worker of the home-screen app: shows the server's notices
theme.js          # picks the saved theme before the stylesheets apply
themes.css        # the 22 Omarchy palettes, copied from the omarchy-terminal-skin skill
terminal.css      # the skin's semantic tokens, copied from the same skill
icon*.png, icon.svg  # home-screen app icons
```

A **section frame** is the sandboxed `<iframe>` an HTML section runs in, with an origin of its own; the frame and the page talk by `postMessage` only. Its head, the messages and the tabs of its kit are in [`docs/html-sections.md`](../../../docs/html-sections.md).
