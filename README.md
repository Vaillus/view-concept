# view-concept

A local page that serves two Claude Code skills. The plan and the explanation stay in one place in the browser, and the conversation stays in the Claude Code terminal. You select passages in the page, comment on them, and send the comments to the session as one batch.

| Skill | What it does in the page |
|---|---|
| `view-concept` (`~/Documents/code/skills/view-concept.md`) | an explanation: it runs `explain-concept` and puts the plan and the prose in the page |
| `view-pr` (`~/Documents/code/skills/view-pr.md`) | a PR review, concepts first, built on `view-concept` (see **A PR review** below) |

Everything goes through Claude Code, so no API key is needed. Side threads are headless `claude -p` runs, billed to the same subscription as the terminal session.

```
terminal (Claude Code)                        browser (view-concept page)
  view-concept · view-pr ─ writes files ──▶  plan · explanation · code · review
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
| `view-concept status <slug> <phase>` | tells the page what Claude is doing; the three `awaiting-*` phases show the button the user answers with |
| `view-concept watch <slug>` | prints each comment batch as it arrives, meant to run under the `Monitor` tool |
| `view-concept pending <slug>` | lists comments not yet resolved |
| `view-concept resolve <slug> c3 b2 --reply "…"` | marks comments or whole batches resolved |
| `view-concept change <slug> "<model change>" --why … --instead … --files …` | records a model change accepted in a PR review (`changes.json`) |
| `view-concept changes [<slug>] [--repo …]` | prints model changes as Markdown bullets, for a PR description's Decisions section |
| `view-concept export <slug>` | writes `~/Documents/Vault/explanations/<title>.md` |
| `view-concept list` / `stop` / `serve` | lists sessions / stops the background server / runs the server in the foreground |

The file formats (`plan.json`, `sections/<id>.md`, `audit.json`, the comment batch) are described in `~/Documents/code/skills/view-concept.md`; what a PR review adds (`"part": 2`, the `approve-model` and `review-code` actions, model changes) in `~/Documents/code/skills/view-pr.md`. The docstring of `store.py` documents the session directory.

## A PR review

`view-pr` runs a code session on the PR branch and reviews the PR through its **model**: the set of concepts the PR introduces or changes (objects, rules, formats, names the code relies on), with their rules and how they fit the existing code. The model lives in the session, in the lexicon of `plan.json` and in Part 1 of the explanation; it is not stored in the repository.

A **model change** is one correction to the model the user accepts during the review, written as an instruction an agent can act on. `view-concept change` records it in `changes.json`, with its reason, what the PR did instead and the files it touches. `view-concept changes` prints the list, which becomes the Decisions section of the PR description.

The review runs in three steps; each one ends on a page element:

| Step | What happens | Page element |
|---|---|---|
| 1 · concepts | Claude writes Part 1 (the model) in the Explanation tab; the user challenges it and each accepted correction is a model change | « Approve model » (status `awaiting-model`) ends the step and starts step 2 |
| 2 · agents | Claude compares the whole model with the code and sends one or more agents to close the gaps; each result goes to « Changes applied to the code » (`q-applied`) | « Review code » (status `awaiting-review`), at the bottom of the Explanation tab, starts step 3 once the user has looked at the commits |
| 3 · code | Claude writes Part 2: one card per item of the diff with a verdict against the model, then a table of every item | the Code tab, which holds every outline item marked `"part": 2` |

A verdict that the code diverges from the model sends the review back to step 2; code that no concept describes sends it back to step 1. The steps, the verdicts and the agents' rules are defined in `view-pr.md`.

## The page

- **Plan / Explanation / Code** (left, one at a time): tabs, or the keys `1`, `2` and `3`. The Code tab shows only in a PR review that has reached Part 2. The page switches to the Plan tab when the plan is waiting for approval, and to the tab of the section being written when writing starts. Otherwise the tab stays where you left it.
  - Under the tab bar, in every tab: « Approve plan » when Claude is waiting for it, or « Approve model » in a PR review (the model is settled and the implementation starts; draft comments go with it). « Approve model » leaves the tab where it is, since the model is read in the explanation.
  - At the bottom of the Explanation tab, after the last section of Part 1: « Review code » in a PR review once the implementation is done (Claude starts the code review, step 3; draft comments go with it). The page does not switch tabs for it.
  - *Plan*: the last revision, the outline with what each section adds (« + comment » on each item), the model changes of a PR review, and the lexicon. Clicking an item opens its section.
  - *Explanation*: one block per outline section. Lexicon terms are underlined, and hovering one shows its developed definition. Terms flagged by the vocabulary audit get a wavy underline. A rewritten section gets an « updated » marker, and the tab shows how many sections were updated. In a code session, `file:line` citations open VS Code.
  - *Code*: the sections of Part 2 of a PR review (outline items with `"part": 2`: the per-item cards, the at-a-glance table, the changes applied to the code), rendered like the explanation. Clicking such an item in the plan, or a comment anchored on one, opens this tab.
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
