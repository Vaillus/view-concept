# CLAUDE.md

A local web page (FastAPI + vanilla JS) for the `explain-concept` skill in `~/Documents/code/skills`. The skill writes session files. The page renders them and sends comment batches back through an inbox file, which `explain-view watch` streams into the Claude Code session under the `Monitor` tool. Usage is in the README.

- The file contract (`plan.json`, `sections/`, `audit.json`, comment batch format) is shared with `explain-concept.md § The workspace`. Change both together. `claude.json` and `threads/` belong to explain-view alone (`threads.py`); the skill only sees the thread line of a batch comment.
- Styling uses the omarchy-terminal-skin tokens only (`themes.css` and `terminal.css` are copies from the skill; don't edit them here).
- Lint, format and type-check must pass: `uv run ruff check --fix . && uv run ruff format . && uv run ty check .`, then `uv run pytest`.
- Never add AI attribution to commits or PRs.
