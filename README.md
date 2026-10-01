# view-concept

A local page for the `view-concept` skill, which runs `explain-concept` in a browser page. The plan and the explanation stay in one place in the browser, and the conversation stays in the Claude Code terminal. You select passages in the page, comment on them, and send the comments to the session as one batch.

Everything goes through Claude Code, so no API key is needed. Side threads are headless `claude -p` runs, billed to the same subscription as the terminal session.

```
terminal (Claude Code)                        browser (view-concept page)
  view-concept skill ───── writes files ──▶  plan · explanation · review
        ▲                                             │
        └── Monitor: view-concept watch ◀── inbox ◀───┘ « Send »
```

## Install

```bash
uv tool install -e ~/Documents/code/view-concept   # puts `view-concept` on the PATH
```

## How a session works

The skill runs these commands. You don't need to run them yourself.

| Command | What it does |
|---|---|
| `view-concept new "<title>" --slug <slug>` | creates `~/.view-concept/sessions/<slug>/` |
| `view-concept open <slug>` | starts the server (port 5080) if needed and opens the page |
| | `new` and `open` also record the Claude Code session that runs them (`claude.json`), which side threads fork from |
| `view-concept watch <slug>` | prints each comment batch as it arrives, meant to run under the `Monitor` tool |
| `view-concept pending <slug>` | lists comments not yet resolved |
| `view-concept resolve <slug> c3 b2 --reply "…"` | marks comments or whole batches resolved |
| `view-concept change <slug> "<model change>" --why … --instead … --files …` | records a model change accepted in a PR review (`changes.json`) |
| `view-concept changes [<slug>] [--repo …]` | prints model changes as Markdown bullets, for a PR description's Decisions section |
| `view-concept export <slug>` | writes `~/Documents/Vault/explanations/<title>.md` |
| `view-concept list` / `stop` | lists sessions / stops the background server |

The file formats (`plan.json`, `sections/<id>.md`, `audit.json`) are described in the skill, `~/Documents/code/skills/view-concept.md`. The docstring of `store.py` documents the session directory.

## The page

- **Plan / Explanation** (left, one at a time): two tabs, or the keys `1` and `2`. The page switches to the Plan tab when the plan is waiting for approval, and to the Explanation tab when writing starts. Otherwise the tab stays where you left it.
  - *Plan*: « Approve plan » (when Claude is waiting for it), or « Approve model » in a PR review (the model is settled and the implementation starts; draft comments go with it), the last revision, the outline with what each section adds (« + comment » on each item), the model changes of a PR review, and the lexicon. Clicking an item opens its section.
  - *Explanation*: one block per outline section. Lexicon terms are underlined, and hovering one shows its developed definition. Terms flagged by the vocabulary audit get a wavy underline. A rewritten section gets an « updated » marker, and the tab shows how many sections were updated. In a code session, `file:line` citations open VS Code.
- **Review** (right, always visible): select text and click « + comment » to add a draft comment (⌘↵ saves it). Drafts survive a reload. « Send » sends all drafts plus an optional note as one batch. Sent comments show « waiting », then « resolved » with Claude's reply.
- **Threads** (in Review): « ask » next to « + comment » on a selection, « ask » on a section, or « + new » for a general question. A thread is a separate conversation: its first turn forks the terminal session (`claude -p --resume <id> --fork-session`), so it knows the discussion so far, and the terminal session never sees it. Threads are read-only (Read, Grep, Glob, no MCP). « → batch » adds a draft comment anchored to the thread's passage; the batch tells the session which thread it comes from. Each turn re-sends the forked history, so a thread on a long session uses a lot of the subscription's limits.
- **Export to vault** (top): writes one Obsidian note. Exporting again overwrites that note, but never a note you wrote yourself with the same title.

The page redraws when a file changes (server-sent events, checked every 0.4 s). KaTeX and Mermaid load from jsdelivr. When offline, maths shows as TeX source and diagrams as code. `?static` in the URL turns off live updates (for headless rendering).

## Configuration

| Variable | Default |
|---|---|
| `VIEW_CONCEPT_HOME` | `~/.view-concept` |
| `VIEW_CONCEPT_VAULT` | `~/Documents/Vault/explanations` |
| `VIEW_CONCEPT_PORT` | `5080` |
| `VIEW_CONCEPT_CLAUDE` | `claude` (the executable side threads run) |

## Development

```bash
uv sync
uv run pytest
uv run ruff check --fix . && uv run ruff format . && uv run ty check .
```

After changing the server code, run `view-concept stop`. The next `open` restarts the server.
