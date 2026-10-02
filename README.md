# view-concept

A local page that serves three Claude Code skills. The plan and the explanation stay in one place in the browser, and the conversation stays in the Claude Code terminal. You select passages in the page, comment on them, and send the comments to the session as one batch.

| Skill | What it does in the page |
|---|---|
| `view-concept` (`skills/view-concept.md`) | an explanation: it runs `explain-concept` and puts the plan and the prose in the page |
| `view-branch` (`skills/view-branch.md`) | a branch review, concepts first, built on `view-concept` (see **A branch review** below) |
| `view-refactor` (`skills/view-refactor.md`) | a triage of existing code: each item gets a triage verdict, then the code is restructured on the current branch or over several PRs (see **A refactor** below) |

`view-concept.md`, `view-branch.md` and `view-refactor.md` in `~/Documents/code/skills/` are symlinks to these three files.

Everything goes through Claude Code, so no API key is needed. Side threads are headless `claude -p` runs, billed to the same subscription as the terminal session.

```
terminal (Claude Code)                                        browser (view-concept page)
  view-concept · view-branch · view-refactor ─ writes files ──▶  plan · explanation · refactor · review
        ▲                                                             │
        └── Monitor: view-concept watch ◀── inbox ◀───────────────────┘ « Send »
```

## Install

```bash
uv tool install -e ~/Documents/code/view-concept   # puts `view-concept` on the PATH
```

## How a session works

The skill runs these commands. You don't need to run them yourself.

| Command | What it does |
|---|---|
| `view-concept new "<title>" --slug <slug> [--kind code --repo … --workflow …]` | creates `~/.view-concept/sessions/<slug>/` |
| `view-concept open <slug>` | starts the server (port 5080) if needed and opens the page |
| | `new` and `open` also record the Claude Code session that runs them (`claude.json`), which side threads fork from |
| `view-concept status <slug> <phase>` | tells the page what Claude is doing; `awaiting-approval`, `awaiting-model` and `awaiting-review` show the button the user answers with |
| `view-concept question <slug> "<question>" [--option … --option …] [--multi]` | puts a Claude question to the user in the page (`questions.json`), sets the phase `awaiting-answer` and prints its id (`q1`) |
| `view-concept watch <slug>` | prints each comment batch as it arrives and nothing else, meant to run under the `Monitor` tool; while it runs it rewrites its heartbeat, `watch.json`, every few seconds |
| `view-concept pending <slug>` | lists comments not yet resolved |
| `view-concept resolve <slug> c3 b2 --reply "…"` | marks comments or whole batches resolved |
| `view-concept change <slug> "<model change>" --why … --instead … --files …` | records a model change accepted in a branch review (`changes.json`) |
| `view-concept changes [<slug>] [--repo …]` | prints model changes as Markdown bullets, for a PR description's Decisions section |
| `view-concept export <slug>` | writes `~/Documents/Vault/explanations/<title>.md` |
| `view-concept list` / `stop` / `serve` | lists sessions / stops the background server / runs the server in the foreground |

A session's **workflow** is the skill that drives it: `view-concept`, `view-branch` or `view-refactor`. `new --workflow` records it in `plan.json`, next to the session's `kind`; it defaults to `view-concept` for an explanation and to `view-branch` for a code session, and `view-branch` and `view-refactor` need a code session. The workflow picks the **verdict set** the page shows: `src/view_concept/verdicts.yaml` holds one list of verdicts per workflow, keyed by its name. A session created before workflows existed has none and gets view-branch's set; an explanation gets none.

The file formats (`plan.json`, `sections/<id>.md`, `audit.json`, the comment batch) are described in `skills/view-concept.md`; what a branch review adds (`"part": 2`, the item fields, `"kind": "finding"`, the `approve-model` and `review-code` actions, model changes) in `skills/view-branch.md`. The docstring of `store.py` documents the session directory.

## A branch review

`view-branch` runs a code session on the branch and reviews it through its **model**: the set of concepts the branch introduces or changes (objects, rules, formats, names the code relies on), with their rules and how they fit the existing code. The model lives in the session, in the lexicon of `plan.json` and in Part 1 of the explanation; it is not stored in the repository.

A **section** is one element of the `outline` list in `plan.json`, with its text in `sections/<id>.md`. A **refactor section** is marked `"part": 2` and shows in the Refactor tab; every other section is an **explanation section** and shows in the Explanation tab.

A **model change** is one correction to the model the user accepts during the review, written as an instruction an agent can act on. `view-concept change` records it in `changes.json`, with its reason, what the PR did instead and the files it touches. `view-concept changes` prints the list, which becomes the Decisions section of the PR description.

The review runs in three steps; each one ends on a page element:

| Step | What happens | Page element |
|---|---|---|
| model consolidation | Claude writes Part 1 (the model) in the Explanation tab; the user challenges it and each accepted correction is a model change | « Approve model » (status `awaiting-model`), at the bottom of the Explanation tab, ends the step and starts model matching |
| model matching | Claude compares the whole model with the code and sends one or more agents to close the gaps; each result goes to the applied changes (`q-applied`) | « Review code » (status `awaiting-review`), at the bottom of the Explanation tab, starts refactoring once the user has looked at the commits |
| refactoring | Claude writes Part 2: one refactor section per **item** of the diff (a file, or several files with one job), with its verdict against the model in its item fields, plus the findings across items | the Refactor tab, which holds every refactor section |

An item's **item fields**, under `item` in its `plan.json` entry, are its `files`, its `verdict` (one of the keys of the session workflow's list in `src/view_concept/verdicts.yaml`, which gives each one's meaning, its `tone` and where it sends the review, in the review table's order), an optional `batch` (a short label or number), the concepts it `implements`, a one-line `note` and its `relations` to other files (`{to, kind, from?}`, where the optional `from` names which of the item's files the arrow starts from, by default its first). A **finding across items** is a refactor section with `"kind": "finding"` and `"items": [<item ids>]`: a problem between items, such as the same logic in two files. Code that no concept describes sends the review back to model consolidation. The steps and the agents' rules are defined in `skills/view-branch.md`.

A verdict's **tone** is the colour the page draws it in, one of `ok`, `danger`, `warn`, `alt`, `flag` and `info`. The page has one style per tone, not per verdict, so adding a verdict is one entry in `verdicts.yaml`; a verdict the list does not know is drawn neutral.

## A refactor

`view-refactor` reviews existing code that was written quickly. It cuts the files it is pointed at into items and gives each one a **triage verdict**, from view-refactor's own list in `verdicts.yaml`: `move`, `split`, `merge`, `throw`, `separate-pr` (the item belongs to a different topic, outside this refactor) and `keep`. Once the user approves the triage, the verdicts are applied on the current branch, or the items are grouped into batches, each one a PR reviewed with `view-branch`; an item's `batch` field names its batch. The steps are defined in `skills/view-refactor.md`.

## The page

- **Plan / Explanation / Refactor** (left, one at a time): tabs, or the keys `1`, `2` and `3`. The Refactor tab shows only in a branch review or a refactor that has reached Part 2. The page switches to the Plan tab when the plan is waiting for approval, and to the tab of the section being written when writing starts. Otherwise the tab stays where you left it.
  - At the bottom of the Explanation tab, after the last section of Part 1, in a branch review: « Approve model » when the model waits for approval (the model is settled and model matching starts), then « Review code » once model matching is done (refactoring starts). Draft comments go with either. The page does not switch tabs for them, since the model is read in the explanation.
  - *Plan*: « Approve plan » (when Claude is waiting for it; draft comments go with it), the last revision, the outline with what each section adds (« + comment » on each), the model changes of a branch review, and the lexicon. Clicking a section in the outline opens it.
  - *Explanation*: one block per explanation section. Lexicon terms are underlined, and hovering one shows its developed definition. Terms flagged by the vocabulary audit get a wavy underline. When Claude rewrites a section, what changed since you last read it stays highlighted: the inserted words get a green background, and every changed paragraph, list item or cell gets a green bar in the margin (a deletion only gets the bar). The section heading and its line in the outline say « updated », and the tab shows how many sections were updated. « updated · mark read » in the heading clears the highlights. What you have read is kept in `seen.json`, so the highlights survive a reload and show changes made while the page was closed. A section's first text is never highlighted. In a code session, `file:line` citations open VS Code.
  - *Refactor*: the refactor sections. At the top, the review table: one item entry per item (its files, a verdict badge coloured by its tone, its batch when any item has one, the concepts it implements with their definitions on hover, the note), the items that need action first and the verdicts counted in the header. Clicking an entry opens its description, the item's section, where comments and threads work as in the explanation. Under it, the structure view, a Mermaid chart drawn from the item fields: one frame per directory, each file outlined in its verdict's tone, files outside the diff greyed out, an arrow per relation, a dashed line per finding across items; the findings are listed under the chart with the items they involve. The applied changes and any other refactor section follow as plain sections. Clicking a refactor section in the plan, or a comment anchored on one, opens this tab and its item entry.
- **Claude questions**: a **Claude question** is a question Claude puts to you in the page instead of the terminal, when it arises from a batch you sent from the page or while Claude waits on the page. Each open one is a card headed « Question from Claude » in the review pane: its text, its options (radio buttons, or checkboxes when several may be picked) and always a free-text field. Several open ones stack in the order Claude asked them, and the browser tab title starts with « ● » while one is open.
- **Review** (right, always visible): select text and click « + comment » to add a draft comment (⌘↵ saves it). Drafts survive a reload. « Send » sends all drafts plus an optional note as one batch. Sent comments show « waiting », then « resolved » with Claude's reply.
- **Threads**: « ask » next to « + comment » on a selection, « ask » on a section, or « ask » in the top bar for a general question. A thread is a separate conversation: its first turn forks the terminal session (`claude -p --resume <id> --fork-session`), so it knows the discussion so far, and the terminal session never sees it. It opens in a popover on its passage; a click anywhere else closes it, and a click on the highlighted passage opens it again. A thread with no passage (a whole section, a general question, or a passage since rewritten) gets a chip instead, in the section heading or the top bar. Threads are read-only (Read, Grep, Glob, no MCP). « → batch » adds a draft comment anchored to the thread's passage; its text is optional (without one, the thread's conclusion is the comment), and the batch tells the session which thread it comes from. « Delete » removes a thread no sent comment points to. Each turn re-sends the forked history, so a thread on a long session uses a lot of the subscription's limits.
- **Listening** (top): « ● Claude listening » while a watch runs for the session, « ○ Claude not listening » when its heartbeat is older than 15 s or missing (between a Monitor expiry and the re-arm, or when Claude stopped watching). The « live » dot next to it only says whether the page is connected to the server. A batch sent while nobody listens waits in the inbox, and the page says so: « Claude isn't listening: write anything in the terminal and it will read this batch ».
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
