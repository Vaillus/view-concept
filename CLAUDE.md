# CLAUDE.md

A local web page (FastAPI + vanilla JS) for two skills in `~/Documents/code/skills`: `view-concept` (runs `explain-concept` in the page) and `view-pr` (a PR review built on `view-concept`). The skills write session files. The page renders them and sends comment batches back through an inbox file, which `view-concept watch` streams into the Claude Code session under the `Monitor` tool. Usage is in the README.

- The file contract (`plan.json`, `sections/`, `audit.json`, comment batch format) is shared with the skills, `~/Documents/code/skills/view-concept.md` and, for what a PR review adds (`"part": 2`, the item fields under `item`, `"kind": "finding"`, the `awaiting-model`/`awaiting-review` phases, the `approve-model`/`review-code` actions, `changes.json`), `view-pr.md`. Change them together. `claude.json` and `threads/` belong to this repo alone (`threads.py`); the skills only see the thread line of a batch comment.
- Styling uses the omarchy-terminal-skin tokens only (`themes.css` and `terminal.css` are copies from the skill; don't edit them here).
- Lint, format and type-check must pass: `uv run ruff check --fix . && uv run ruff format . && uv run ty check .`, then `uv run pytest`.
- Never add AI attribution to commits or PRs.
