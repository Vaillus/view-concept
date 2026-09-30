# explain-view

A local page for the `explain-concept` skill. The plan and the explanation stay in one place in the browser, and the conversation stays in the Claude Code terminal. You select passages in the page, comment on them, and send the comments to the session as one batch.

Everything goes through the Claude Code session, so no API key is needed.

```
terminal (Claude Code)                        browser (explain-view)
  explain-concept skill ── writes files ──▶  plan · explanation · review
        ▲                                             │
        └── Monitor: explain-view watch ◀── inbox ◀───┘ « Send »
```

## Install

```bash
uv tool install -e ~/Documents/code/explain-view   # puts `explain-view` on the PATH
```

## How a session works

The skill runs these commands. You don't need to run them yourself.

| Command | What it does |
|---|---|
| `explain-view new "<title>" --slug <slug>` | creates `~/.explain-view/sessions/<slug>/` |
| `explain-view open <slug>` | starts the server (port 5080) if needed and opens the page |
| `explain-view watch <slug>` | prints each comment batch as it arrives, meant to run under the `Monitor` tool |
| `explain-view pending <slug>` | lists comments not yet resolved |
| `explain-view resolve <slug> c3 b2 --reply "…"` | marks comments or whole batches resolved |
| `explain-view export <slug>` | writes `~/Documents/Vault/explanations/<title>.md` |
| `explain-view list` / `stop` | lists sessions / stops the background server |

The file formats (`plan.json`, `sections/<id>.md`, `audit.json`) are described in the skill, `explain-concept.md § The workspace`. The docstring of `store.py` documents the session directory.

## The page

- **Plan / Explanation** (left, one at a time): two tabs, or the keys `1` and `2`. The page switches to the Plan tab when the plan is waiting for approval, and to the Explanation tab when writing starts. Otherwise the tab stays where you left it.
  - *Plan*: « Approve plan » (when Claude is waiting for it), the last revision, the outline with what each section adds (« + comment » on each item), the decisions of a code session, and the lexicon. Clicking an item opens its section.
  - *Explanation*: one block per outline section. Lexicon terms are underlined, and hovering one shows its developed definition. Terms flagged by the vocabulary audit get a wavy underline. A rewritten section gets an « updated » marker, and the tab shows how many sections were updated. In a code session, `file:line` citations open VS Code.
- **Review** (right, always visible): select text and click « + comment » to add a draft comment (⌘↵ saves it). Drafts survive a reload. « Send » sends all drafts plus an optional note as one batch. Sent comments show « waiting », then « resolved » with Claude's reply.
- **Export to vault** (top): writes one Obsidian note. Exporting again overwrites that note, but never a note you wrote yourself with the same title.

The page redraws when a file changes (server-sent events, checked every 0.4 s). KaTeX and Mermaid load from jsdelivr. When offline, maths shows as TeX source and diagrams as code. `?static` in the URL turns off live updates (for headless rendering).

## Configuration

| Variable | Default |
|---|---|
| `EXPLAIN_VIEW_HOME` | `~/.explain-view` |
| `EXPLAIN_VIEW_VAULT` | `~/Documents/Vault/explanations` |
| `EXPLAIN_VIEW_PORT` | `5080` |

## Development

```bash
uv sync
uv run pytest
uv run ruff check --fix . && uv run ruff format . && uv run ty check .
```

After changing the server code, run `explain-view stop`. The next `open` restarts the server.
