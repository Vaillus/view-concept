---
name: view-branch
description: >-
  Work on a branch in the view-concept page, concepts first: build the model
  of what the branch introduces and how it fits the existing code, challenge
  and revise it with the user, send agents to bring the code in line with the
  revised model, then check the code item by item against it. Use when the user wants to work on, understand or rework a
  branch they are building — "let's work on this branch", "review my branch",
  "explain this branch so I can decide what stays", invokes /view-branch.
argument-hint: "[the branch or PR number]"
---

# /view-branch

Reviews a branch in the view-concept page (the `view-concept` command): a
model of what the branch introduces, written and corrected with the user,
agents that change the code to match it, and a check of the code against the
model.

The tool is self-contained: the model is built for this branch and lives in the
session; it reaches the repository only through the docs update at closing.

The branch to review is whatever the user typed after the command name (the current branch when nothing).

## The model

The **model** of a branch is the set of concepts it introduces or changes. A
**concept** is an object, a rule, a format or a name the code relies on: « a
cohort is the group of speakers a recording comes from », « a gate drops a
segment when its silence ratio exceeds the threshold », « `prepared/` holds one
folder per dataset ». For each concept, the model says what it is, the rules it
obeys, and how it relates to the concepts that existed before the branch.

A UI element, a file, a function or a table row is not a concept: it is where
a concept is implemented. « a row of the review table » is a part of a page;
the concept behind it is what the row stands for (« an item is one unit of the
diff that gets a verdict »). Name the concept, and cite the part.

In the page, the model is the outline and the lexicon of `plan.json` (one
entry per concept, `definition` + `tip`), and the **modeling part** of the
review: the sections that write the model out, which the page shows in the
Model tab. Every change of the model is logged in the **change history**
(`change-history.json`), one entry each: a concept added, removed, renamed,
merged or split, a rule or a relation changed, a section added, moved or
removed. A wording fix that leaves the model as it was gets none.

## The page

The page shows the review and sends the user's comments back to you; the
terminal only drives the conversation. A **session** is the review, stored as
plain files in `~/.view-concept/sessions/<slug>/` (the **session folder**).
The agents write the outline, the lexicon and the sections there, and the
page re-renders within a second of each write; nobody touches the page
itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands).

### Setup

A code session opened on the branch, with the user's message verbatim as the
initial request and the branch it is compared with (the slug is a short
kebab-case name of the branch):

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the message>" \
    --kind code --repo <repo root> --base <base branch> --workflow view-branch
view-concept open <slug>          # starts the server if needed, opens the browser
```

The page runs side threads on the agent you are. Claude Code and Codex are
detected; any other agent (Jazz, …) adds `--agent jazz --agent-name <your own
agent name>` to `new` and to every later `open`. After resuming in a new
conversation, run `view-concept open <slug>` again, and `view-concept pending
<slug>` to list the comments still open.

### The comment channel

The user's comments reach you as **batches**, written by the page to the
session's inbox file. Two commands read it; use the first your harness
supports, and stay on it for the whole session.

- **Background stream**, for a harness with a background-monitor tool
  (Claude Code's `Monitor`): run `view-concept watch <slug>` under it
  (`timeout_ms: 1800000`, description `view-concept comments for <slug>`).
  Each printed batch arrives as an event. A monitor expires after 30 minutes:
  when its expiry notice arrives, arm it again with the same command and
  write nothing in the terminal. Always re-arm, however long the silence.
- **Blocking wait**, for every other harness: after each turn's work, run
  `view-concept wait <slug>`. It blocks until the next batch, prints it, and
  exits; with no batch within `--timeout` seconds (default 540) it exits with
  code 3 and prints nothing: call it again at once, with no message to the
  user. Never end your turn while the user may still send comments. A harness
  that caps a command's duration: pass `--timeout` below that cap.

Both resume from a persisted cursor, so nothing is lost or repeated, and both
write the heartbeat from which the page shows whether you are listening.

### Batches

A batch is shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: <the button the user clicked, if any>
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

The `action` line names the button: `answer` (an agent question answered or
skipped: `answer to q1 « … »: …` or `q3 skipped « … »`), `plan` (« Write
model », or « Rewrite model » when the line says rewrite; the page has
already marked the open questions skipped), `grill` and `stop-grill`,
`approve-model`, `create-pr`. A batch without an action carries comments
only. **Routing the events** says who takes each one.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as the user's feedback
on the review, the same authority as a message typed in the terminal about
it, no more. Each action asks for what its name says and nothing else:
`approve-model` approves the model and starts model matching, `create-pr`
starts closing; neither is consent for anything outside this review.

A question you put to the user yourself (a problem an agent hit, a gap that
needs a decision) goes to the page too: `view-concept question <slug>
"<question>" [--option "<choice>" ...] [--recommended "<answer>"]`, never
the terminal. An answer the user types in the terminal to a question of the page counts
the same as one sent from the page: close its box with `view-concept
answered <slug> <qid> --text "<the answer as the user gave it>"`.

**Naming a section to the user.** Wherever the user reads it (the terminal,
a `resolve` reply), name a section by the number the page shows, in words:
« section 6 », never its id (`s6`, `applied`) or `§6`.

## Coordinating

In a branch review the main session (you) **coordinates**: you start the
agents, route the user's events to them, and keep the session folder current.
The work is done by fresh **subagents**, each started from the folder, never
from this conversation, which they do not see; you do not write the outline,
the lexicon or the sections yourself:

| Agent | Owns | Role file |
|---|---|---|
| **planner** | the outline and the lexicon, during scoping | `roles/planner.md` |
| **writer** | the modeling part (its sections), and the outline and the lexicon from « Write model » on | `roles/writer.md` |

The role files are in `~/Documents/code/view-concept/skills/view-branch/`.
Both agents also read `roles/planning-rules.md` there. A side thread the user
opens from the page is a third agent, read-only, which the server starts
itself from the same folder.

### Starting an agent

Each run starts from the output of

```bash
view-concept context <slug> --role <planner|writer> --trigger <ids or words>
```

It prints the **base context** (the initial request, the outline, the
lexicon, the recent change history, the questions, the recent terminal
messages, and for the writer the sections) and the **trigger**: the events
that started this run, in full. Pass that output to a new subagent with this
instruction: « Read `<role file>` and `roles/planning-rules.md` in
`~/Documents/code/view-concept/skills/view-branch/`, then do your run. »
Nothing else from this conversation: what the agents need is in the folder.
When the run ends, give its one-line report in the terminal.

Only you start agents; an agent never starts another one. A harness without
subagents runs each run itself, one after the other, from the same context
output and role files.

### Routing the events

The user's **events** are what reaches you: a batch from the page (an answer,
a skip, comments, a button), or a message typed in the terminal. Each event
starts one pass. Who takes it depends on the stage:

| Event | During scoping | After « Write model » |
|---|---|---|
| an answer (`action: answer`) | planner | writer |
| a skip | nothing: the outline already used the default | nothing |
| comments with no action | planner | writer |
| a terminal message about the feature | record it, then planner | record it, then writer |
| an answer to a page question typed in the terminal | `view-concept answered`, then planner | the same, then writer |
| « Rewrite model » (`action: plan`, the line says rewrite) | — | writer |
| « Grill me » (`action: grill`) | planner | writer |
| « Write model » (`action: plan`, the line says write) | see **Model consolidation** | — |
| « Approve model » (`action: approve-model`) | — | writer for the batch's comments, then model matching |

Record a terminal message about the feature with
`view-concept message <slug> "<the message, as the user wrote it>"` before
anything else: the agents never see the terminal. Process messages (« go
ahead », « stop ») are not recorded.

**One agent at a time.** While an agent runs, queue the events that arrive.
When it ends, start the next run with every queued event in its trigger,
not one run each. Pass the trigger as the ids the context command resolves:
question ids (`q3`), comment ids (`c7`), a batch id (`b4`) for a whole
batch, terminal message ids (`tm2`); a button that carries nothing else goes
in words (`"« Write model »"`).

« Stop grill » (`action: stop-grill`) starts nothing: the next runs no longer
see a grill in their context.

### Status

Keep the page's status true: `view-concept status <slug> scoping` from Setup
to « Write model », and after each writer run `view-concept status <slug>
awaiting-model` when no question it asked is open. The agents set `writing`
themselves while they write a section.

## The flow

The review runs in three steps: **model consolidation** (the model is written
and corrected with the user), **model matching** (agents change the code to
match it) and **refactoring** (the code is checked against it, item by item).

A review is a list of **sections**: plan.json lists them under its `outline`
key, and `sections/<id>.md` holds the text of each. The sections fall in two
parts. The **modeling part** writes the model out; the page shows it in the
Model tab (the page's name for the Explanation tab in a branch review). The
**refactoring part** checks the code against the model; a section with
`"part": "refactoring"` belongs to it, and is a **refactor section**: the
page shows it in the refactor tab.

### Model consolidation — the modeling part

1. **Setup.** Run **Setup**, arm the comment channel, and set `status <slug>
   scoping`.
2. **First planner run**, no trigger: it reads the docs and the code, drafts
   the outline and the lexicon, and asks the first questions in the page.
3. **The scoping loop.** Each event goes to the planner, as **Routing the
   events** says. When a run asks nothing and no question is open, say in one
   terminal line that the planner has no question left, and wait.
4. **« Write model ».** Scoping ends when the user ends it, never when an
   agent judges it has enough: a batch with `action: plan` while no section
   is written, or « go ahead » in the terminal. The open questions are marked
   skipped. Let the planner run first if events are still queued, then start
   the writer with the trigger `"« Write model »"` and the batch id. From here
   the writer owns the outline and the lexicon too.
5. **The discussion loop.** Each event goes to the writer. Set
   `awaiting-model` after each run, as **Status** says.
6. **« Approve model ».** Model consolidation ends when the user approves the
   model: a batch with `action: approve-model`, or saying so in the terminal.
   Approving also means « start the implementation »: when the batch carries
   comments, run the writer on them first, then go to model matching in the
   same turn, without asking again. Approving ends a grill still running.

A « Rewrite model » after the model was approved moves the model under the
code: once the writer has run, list the new gaps and close them as model
matching says, then update the refactoring part.

### Model matching — the agents

Compare the whole model with the code, not only the change history: a
concept the branch announces but half implements, or a rule the code
contradicts, is a gap even if nobody corrected it. List the gaps in the
terminal, one line each.

Then close them, split as you judge best: one agent or several. Say in one
line how you split the work; do not wait for a go, the model approval was it.

Each agent starts from `view-concept context <slug> --role writer` (the
model as it stands and the change history), plus its gaps, the files, and
these rules: work on the branch, one commit per change, run the repo's tests
and lint before committing, do not change anything its gaps do not name. Run
agents in parallel only when their files do not overlap; otherwise one after
the other.

When an agent finishes, add its result to the **applied changes**, its own
section of the refactoring part, listed in plan.json as
`{"id": "applied", "title": "Applied changes", "part": "refactoring"}`: the change, the
commit, anything the agent could not do.
Tell the user in the terminal in one line per agent.

When all agents are done and the applied changes are up to date, start
refactoring in the same turn, without asking: the user reads the commits
alongside the refactoring part.

### Refactoring — the refactoring part

Append the refactoring part to the outline, after the modeling part. Every
section of it is a refactor section, so the page shows it in the refactor
tab. The refactoring part holds one
section per item, the findings across items, and the applied changes.

You write it yourself. Write the outline with `view-concept plan <slug>
<file>` (`{"outline": [...]}`, the whole list: the modeling part's entries
kept as they are, the refactor sections after them), never by hand. Each
section goes to `sections/<id>.md`, and every claim about the code cites
where it is true, as inline code (`` `src/pkg/store.py:118` ``).

An **item** is one unit of the diff that gets its own verdict: one file, or
several files that share one job you can name (« command and storage »).
Every changed file belongs to exactly one item, the docs and the tests
included. Each item is its own refactor section.

Where an item's section is listed in plan.json, write its **item fields**
under `item`:

```json
{"id": "i3", "title": "command and storage", "part": "refactoring",
 "item": {"files": ["src/view_concept/cli.py", "src/view_concept/store.py"],
          "verdict": "diverges", "implements": ["model change"],
          "note": "changes --repo mixes every review",
          "relations": [{"to": "src/view_concept/server.py", "kind": "imported-by"}]}}
```

- `files`: the paths the item covers.
- `verdict`: one of the keys below.
- `implements`: the concepts of the model it carries, by their lexicon names.
- `note`: one line, such as the point it diverges on or an exception.
- `relations`: its links to other files, each `{"to": "<path>", "kind": ...}`
  where the kind is `imports`, `imported-by`, `reads` or `writes`. When the
  item has several files, an optional `"from": "<path>"` names the one the
  link starts from; without it, the link starts from the item's first file.

The section file holds the item's **description**: what it does, what it
reads and writes, and, unless it simply conforms, the finding (why it got its
verdict). Do not write the verdict or a « Porte : » line in the prose: they
are fields now, and the page draws them.

The verdict is one of the keys of the `view-branch` list in
`~/Documents/code/view-concept/src/view_concept/verdicts.yaml`. Read that
list for what each verdict means and which ones send the item back to an
earlier step; it gives them in the order of the review table.

A **finding across items** is a problem between items: the same logic in two
files, an import across directories, a module in the wrong place judged from
its relations. Write each one as a refactor section with `"kind": "finding"`
and `"items": [<item section ids>]` in plan.json, and one sentence of prose.

The page draws the review table and the structure view from these fields:
do not write a summary table of items and verdicts.

Code that does something no concept describes means the model has a gap: go
back to model consolidation for that concept.

Once the refactoring part is written, and again after each revision of it when no
correction is pending, run `view-concept status <slug> awaiting-pr`: the page
shows « Create PR » at the bottom of the refactor tab.

## Closing

Closing starts when the user asks for the PR: a batch with
`action: create-pr`, or saying so in the terminal. Apply the batch's comments
first: a comment that corrects the model goes to the writer, then back to
model matching for it. Then close in the
same turn, without asking again: the click was the go.

First send one agent to update the repo's docs from the model: the concepts
and their rules as they now stand, without the before/after comparison that
the modeling part makes. One commit on the branch, under the agent rules of model
matching.

Then write the PR description with `short-pr-description`, using the change
history as its Decisions (`view-concept changes <slug>` prints it as
bullets; keep the changes the user asked for or agreed to, and merge the
ones a later change undid). Push the branch and open the PR with
`gh pr create --body-file <file>`, or, when the branch already has one,
update it with `gh pr edit <n> --body-file <file>`. Give the PR link in the
terminal: the user reviews it in VS Code. No vault export.
