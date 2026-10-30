# view_concept

The Python package behind the `view-concept` command: the command line the skills call (a skill is a `SKILL.md` file of instructions an agent loads when you name it), the FastAPI server that serves the page, the local web page that renders a session's files in the browser and sends your comments back to the agent, and the storage of each session, one explanation or review with its files and comments, kept in `~/.view-concept/sessions/<slug>/`.

## Files

```
cli.py         # the `view-concept` command (entry point `main`), one subcommand per action of a skill
store.py       # session storage: the layout of a session folder and every read and write of its files
server.py      # the local web server: the page, file-change streaming, comment batches, side threads, the parameters file, the channel's requests
verdicts.yaml  # the verdicts an item can get, one list per workflow, each with the colour the page draws it in
context.py     # the context a role agent of an explanation or a feature, or a side thread, starts from
threads.py     # side threads: headless agent turns started from the page
channel.py     # the channel: a section's script asks a small agent for data, held to a JSON schema
agents.py      # the agent backends side threads and the channel's small agents run on (Claude Code, Codex, any command)
frame.py       # the section frame an HTML section is drawn in: its injected head and sandbox flags
render.py      # the Markdown renderer shared by the page and the published page
publish.py     # publishing an explanation as a read-only page in a GitHub pages repo
metrics.py     # run metrics of a feature, read from Claude Code transcripts and the session files
gate.py        # the tailnet gate on the remote port: only the owner's Tailscale login gets through
push.py        # web push notices to a phone when a session starts waiting for the user
launch.py      # starts a new agent session from the page in a terminal window
static/        # the page's HTML, CSS and JavaScript (README)
```

## Usage

The commands, the session files and the environment variables are in [`docs/reference.md`](../../docs/reference.md); `store.py`'s module docstring lists every file of a session folder and who writes it.

## Pins

A **pin** is a record of an open point on an element of the drawing, kept in the pin file, that the scoper closes once it is settled: the drawing is a session's scoping section, which the scoper, a role agent, builds with you before any prose, and an element is one piece of it, with an id of its own. The **pin file** is `pins.json` in the session folder: every pin of the session, open and closed.

- Each skill places its own kinds, listed in `store.py` (`PIN_KINDS`): `/build-feature` a hole or a supposition, `/view-concept` a probe, a correction, a tension, a choice or a lead. `view-concept pin` refuses a kind the session's skill does not place, so a kind a scoper's role file adds needs its entry there, its place in `PIN_TONE_ORDER` and its colour in `static/app.css` and `static/frame.css`.
- « End scoping » is refused while a correction, a tension, a hole or a supposition is open (`BLOCKING_PINS`): the server refuses the batch, and the page, which takes both lists from the server's state, disables the button.
- A pin opened after « End scoping » sets the phase back to `scoping`.
- A session written before pins has `holes.json`: it is moved to `pins.json` the first time the session is read, and a comment anchored `hole:<id>` reads as `pin:<id>`.

## The channel

The **channel** is the path a section's script uses to ask an agent for data: frame, page, server, small agent, and back. Only an HTML section's script uses it. Inside the section's frame, `static/frame.js` gives the script `viewConcept`, whose calls each return a Promise:

- `viewConcept.load()` resolves with `{saved, received}`, the section's entry of the parameters file;
- `viewConcept.save(saved)` replaces `saved`, an object;
- `viewConcept.ask(key, instruction, schema)` resolves with the answer, data held to the JSON schema `schema`.

The page (`frameChannel` in `static/app.js`) passes each call to the server. For `ask`, `channel.py` starts a **small agent**, a headless, read-only agent the server starts to answer one request of the channel, on the side threads' backend (`agents.py`), with the context a side thread on that section gets. The server holds the answer to the schema (by the agent's own schema option where it has one, by checking the JSON of its text otherwise), keeps it under `key`, which a later request with the same key replaces, and returns it. A failure (no answer within `CHANNEL_TIMEOUT`, an answer that breaks the schema) rejects the script's Promise with an Error.

The **parameters file** is `params.json` in the session folder, kept by the server for the sections that use the channel: what each one's script saved and the answers it received, `{<section id>: {saved, received: {<key>: <answer>}}}`. The page writes `saved`, the server `received`, and no skill writes it; the scoper, the planner and the writer read it in their context. An entry holds at most `PARAMS_LIMIT` bytes, and a change of the file never re-renders the page.

A published page has no server: `publish.py` writes the entry of each published HTML section into the page, and `static/reader.js` answers from it, `load` with that entry, `save` in that page only, `ask` with the answer received before publishing. A key never received rejects with an Error named `NotReceivedError`, on which a script draws nothing. An answer received after publishing makes the published page out of date. `reader.js` mirrors `app.js`'s `frameChannel`: change them together.
