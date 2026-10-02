# CLAUDE.md

A local web page (FastAPI + vanilla JS) for two skills kept in `skills/`: `view-concept` (runs `explain-concept` in the page) and `view-branch` (a branch review built on `view-concept`). The skills write session files. The page renders them and sends comment batches back through an inbox file, which `view-concept watch` streams into the Claude Code session under the `Monitor` tool. Usage is in the README.

- The file contract (`plan.json`, `sections/`, `audit.json`, comment batch format) is shared with the skills, `skills/view-concept.md` and, for what a branch review adds (`"part": 2`, the item fields under `item`, `"kind": "finding"`, the `awaiting-model`/`awaiting-review` phases, the `approve-model`/`review-code` actions, `changes.json`), `skills/view-branch.md`. Change them together. `claude.json`, `threads/` (`threads.py`) and `seen.json` (what the user has read) belong to this repo alone; the skills only see the thread line of a batch comment.
- Styling uses the omarchy-terminal-skin tokens only (`themes.css` and `terminal.css` are copies from the skill; don't edit them here).
- Lint, format and type-check must pass: `uv run ruff check --fix . && uv run ruff format . && uv run ty check .`, then `uv run pytest`.
- Never add AI attribution to commits or PRs.
