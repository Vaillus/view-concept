# CLAUDE.md

- Each skill in `skills/` is self-contained: it carries every rule it follows and never sends the agent to read another skill, so a rule shared by two skills is written in both. The one exception: build-feature's implementer and review-docs follow `skills/write-readme/SKILL.md` for a README.
- The skills write the session files and call the `view-concept` commands: a change to a session file's format, a command, a phase or a batch action is a change to every skill that uses it (`grep` the name in `skills/`). The layout of a session folder is in `store.py`'s module docstring. The formats of `agent.json`, `threads/`, `watch.json`, `seen.json`, `drafts.json` and `published.json` belong to this repo alone: no skill describes them.
- `static/reader.js` (the published page's script) mirrors functions of `static/app.js` (term underlining, maths, Mermaid, the tooltip): change them together.
- Styling uses the omarchy-terminal-skin tokens only (`themes.css` and `terminal.css` are copies from the skill; don't edit them here).
- Lint, format and type-check must pass: `uv run ruff check --fix . && uv run ruff format . && uv run ty check .`, then `uv run pytest`.
- Never add AI attribution to commits or PRs.
