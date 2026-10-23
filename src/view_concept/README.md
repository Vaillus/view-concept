# view_concept

The Python package behind the `view-concept` command: the command line the skills call, the FastAPI server that serves the page, and the storage of each session, one explanation or review with its files and comments, kept in `~/.view-concept/sessions/<slug>/`.

```
cli.py         # the `view-concept` command (entry point `main`), one subcommand per action of a skill
store.py       # session storage: the layout of a session folder and every read and write of its files
server.py      # the local web server: the page, file-change streaming, comment batches, side threads
verdicts.yaml  # the verdicts an item can get, one list per workflow, each with the colour the page draws it in
context.py     # the context a subagent of a feature, or a side thread, starts from
threads.py     # side threads: headless agent turns started from the page
agents.py      # the agent backends a side thread runs on (Claude Code, Codex, any command)
frame.py       # the section frame an HTML section is drawn in: its injected head and sandbox flags
render.py      # the Markdown renderer shared by the page and the published page
publish.py     # publishing an explanation as a read-only page in a GitHub pages repo
metrics.py     # run metrics of a feature, read from Claude Code transcripts and the session files
gate.py        # the tailnet gate on the remote port: only the owner's Tailscale login gets through
push.py        # web push notices to a phone when a session starts waiting for the user
launch.py      # starts a new agent session from the page in a terminal window
static/        # the page's HTML, CSS and JavaScript (README)
```

The commands, the session files and the environment variables are in [`docs/reference.md`](../../docs/reference.md); `store.py`'s module docstring lists every file of a session folder and who writes it.
