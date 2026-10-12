---
name: view-refactor
description: >-
  Review a part of the codebase that was written quickly in the view-concept
  page, decide what stays, and restructure it: map the scope, give each item a
  triage verdict and its destination, have the user approve the triage, then
  either apply it on the current branch or split the work into batch PRs that
  are reviewed one by one. Use when the user wants to clean up, triage or
  restructure vibe-coded or experimental code — "help me decide what to keep
  in X", "triage this folder", "clean up X before I PR it", "refactor this
  module", invokes /view-refactor.
argument-hint: "[the files or folder to review]"
---

# /view-refactor

Triages existing code in the view-concept page (the `view-concept` command):
a model of what the scope is, a verdict for each item of it, approved by the
user, then agents or PRs that apply the verdicts, and a check of the result.
You write the plan and the sections yourself.

The code to refactor is whatever the user typed after the command name.

The terminal is a bad place to read a review: every new message pushes it
further up the scrollback. So the plan and the sections live in the page, and
the terminal only drives the conversation. The user reads in the page, and
sends comments on selected passages back to this session in batches.

A **session** is the review, stored as plain files in
`~/.view-concept/sessions/<slug>/`. You write the plan and the sections; the
page re-renders within a second of each write; you never touch the page
itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands).

## The flow

1. **Setup**: open the session and the page, arm the comment channel.
2. **Scoping**: settle the scope and read the code, asking the user in the
   page; « Write model » ends it.
3. **The modeling part**: the outline and the lexicon, approved by the user,
   then the sections and the vocabulary audit.
4. **The triage**: one refactor section per item, with its verdict and
   destination, approved by the user (« Approve model »).
5. **Small or big refactor**: the verdicts applied on the branch, or batch
   PRs planned.
6. **Closing.**

The user owns the repository and the goal is fixed (decide what stays, and
restructure it): never ask their level, their goal, or whether they know a
prerequisite.

## Setup

The slug is a short kebab-case name of the scope.

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the user's request, verbatim>" \
    --kind code --repo <repo root> --workflow view-refactor
view-concept open <slug>          # starts the server if needed, opens the browser
```

The workflow makes the page use view-refactor's verdicts. The page runs side
threads on the agent you are. Claude Code and Codex are detected; any other
agent (Jazz, …) adds `--agent jazz --agent-name <your own agent name>` to `new`
and to every later `open`. After resuming in a new conversation, run
`view-concept open <slug>` again: it records the current conversation as the
one side threads fork from. `view-concept pending <slug>` lists the comments
still open.

Then arm the comment channel and run `view-concept status <slug> scoping`.

## The comment channel

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

## Scoping

### Scope

The **scope** is the files the user points at (a folder, a module, a list of
scripts), plus one sentence on what is not reviewed: sibling folders, shared
libraries the scope imports, callers outside it. Ask for the scope when the
argument does not give it. Write the boundary sentence in the proposal section
of the modeling part.

### Ground it

Read the repo's docs first (README files, a `docs/` folder, module
docstrings), then, for every file of the scope:

1. its imports, and who imports it, inside and outside the scope;
2. what it reads and writes: files, folders, tables, and which of them are raw
   inputs and which are outputs of another item;
3. its git history: which commit introduced it, and whether a later commit
   supersedes it (`git log --follow -- <path>`);
4. what uses it: entry points, commands, the scripts in `pyproject.toml` or a
   Makefile, CI, tests.

Code that nothing in the repo calls may still be run by hand. Ask the user
rather than guess: one question listing every such file, before the triage.

### Questions in the page

Do not skip scoping: scope the refactor before the modeling part is written.
Every question you put to the user goes to the page (see **Agent questions**),
never to the harness's terminal question tool: the scope, the code nothing
calls, and whatever the reading left open. Ask every question you judge
relevant, the frontier first. A question whose answer would not change what
you write is not worth asking; one the code or a command can answer is not
one for the user. Then end your turn, listening, and handle each answer batch
as it arrives: ask the questions it opens.

**End of scoping.** Scoping ends when the user ends it, never when you judge
you have enough: a batch with `action: plan` (« Write model » in the scope
block), or « go ahead » in the terminal. Treat every question still open as
skipped (after « Write model », the page has already marked them so), and
write the outline and the lexicon in the same turn. When every question is
answered and you have none left to ask, say so in one terminal line and wait
for the user to end scoping.

## The modeling part — what the scope is

### Outline and lexicon

Run `view-concept status <slug> planning`. The outline starts with this fixed
skeleton, in this order:

1. **Today.** The scope on one real example: a script run with its output, a
   file it writes, a chain of imports. Only the vocabulary the code has.
2. **What goes wrong.** The problems the example shows, in the user's terms:
   duplicated logic, a file doing several jobs, code nothing reads, a module
   in the wrong place.
3. **The proposal.** A mockup of the triage (the review table with a few of
   the real items, their verdicts and, in the big case, their batch) and a
   Mermaid diagram of the flow. Give the scope's boundary sentence here.
4. **One section per shared concept**: a concept that several items of the
   scope implement, such as « a sweep runs one evaluation over a grid of
   thresholds ». These are the lexicon entries, and they are what merge
   verdicts rest on.

Each outline entry is `{"id": "s1", "title", "earns"}`, `earns` saying what
the section gives the sections after it. The lexicon has one entry per term
the sections will use, `{"term", "section", "definition", "tip"}`: the
section that introduces it (its **home section**), the one-line definition
you will give there, and the hover text (written with the section).

The lexicon is a contract in both directions: every term in it is introduced
in its home section and used freely after, and **every technical term in the
sections is in the lexicon**. A term you are about to write that is not in it
gets added with a definition, or the sentence goes. When a term's natural
definition point comes later than its first use, the outline is wrong:
reorder it, do not patch it in prose.

Write them with `view-concept plan <slug> <file>` (or `-` for stdin), the
file being `{"outline": [...], "lexicon": [...]}`, either key alone when only
one changes. Each key replaces the whole list. Never edit `plan.json` by
hand: it holds the initial request, the repo and the workflow too.

Section ids are stable: when you reorder, keep each section's id and change
its position. The page anchors the user's comments to ids.

**The precedence rule.** Every text about a term (its introducing prose, its
`definition`, its `tip`) uses only terms whose home section is at or before
its own. When it needs a later term, reorder the outline or say the idea in
plain words; never point ahead (« see section 7 »). A term spelled like a
common word counts as used wherever the word appears. A **forward reference**
is a `definition` or `tip` that uses a later term; an **early use** is a term
in the prose of a section placed before its home section.

**The lexicon texts.** The page shows a term's `tip` when the reader hovers
any use of it, and falls back to `definition` without one. Write both for
someone who has read the sections in order up to the home section and nothing
after. Both obey the precedence rule, carry no location details (a file, a
key, a section number: those go in the home section's prose, as citations),
and do not repeat what other entries define.

### Plan approval

In one terminal line, say what the plan covers, and put one or two sentences
in `revision` of `plan.json` (the page shows it above the outline) on what
the scoping answers changed. Run `view-concept status <slug>
awaiting-approval` (the page shows « Approve plan ») and stop. Write the
sections only after the user replied: a terminal message, or a batch with
`action: approve-plan`. Anything the user says about the plan binds it.

### The sections

Each section goes to `sections/<id>.md`, in outline order: Markdown, no
heading of its own (the page renders the title), ```` ```mermaid ```` for
diagrams. Run `view-concept status <slug> writing --section <id>` before each
one. In the terminal, one line saying the modeling part is written, never the
prose.

- **Citations are required.** Every claim about the code cites where it is
  true, as inline code: `` `src/pkg/store.py:118` `` (path relative to the
  repo root, `:line` or `:start-end`). The page turns each citation into a
  link to the file. A claim you cannot cite is a claim you have not checked:
  check it or cut it.
- **Short.** Each section gives its core in eight lines of prose or fewer, in
  full sentences, never in bullet fragments; a table or a diagram replaces
  prose where it can. Before showing the modeling part, count the lines of
  prose of every section (tables, code blocks and diagrams don't count) and
  cut any over eight.
- **Honour the lexicon**, and write each term's `tip` with its home section.
- **Mechanism before abstraction.** Show a concept on the real example of the
  first sections before stating it in general. Never let a metaphor stand in
  for a mechanism you can show.
- **Say why the concept earns its name**: what it lets the user see, predict
  or decide. One sentence. **Say what it is not**, in a clause, when a
  neighbouring concept could be mistaken for it.
- **A diagram** when the structure is a sequence or a containment that prose
  serialises badly; never one that re-renders a list.
- Write in the language of the initial request, technical terms as the code
  names them. Name a section to the user by its number in words
  (« section 6 »), never by its id (`s6`, `applied`) or `§6`.

### The audit

Run `view-concept status <slug> audit`, then:

1. `view-concept check <slug>` writes every forward reference and early use
   to `audit.json` (issues `forward` and `early`). Fix each one by the
   precedence rule.
2. Re-read every section for the words that slipped past the lexicon, and add
   each one to `audit.json` (`[{"term", "section", "issue", "note"}]`, keeping
   the entries `check` wrote), with one of these issues: `undefined` (a
   domain term absent from the lexicon), `metaphor` (a word that names an
   intuition instead of the mechanism), `ambiguous` (an overloaded word whose
   meaning depends on context the reader may not share), `assumes-context` (a
   bare reference to something the text has not introduced).
3. The page underlines each term. Give the count and a one-line list in the
   terminal. Fix only the ones the user agrees on, by the precise term, an
   inline definition or a disambiguating clause, and update the lexicon.

Go on to the triage in the same turn.

## The triage — the refactoring part

The refactoring part comes after the modeling part in the outline. Every
section of it has `"part": "refactoring"`, so the page shows it in the
refactor tab: one section per item, the findings across items, and, in a
small refactor, the applied changes.

An **item** is one unit of the scope that gets its own verdict: one script,
or several files that share one job you can name (« command and storage »).
Every file of the scope belongs to exactly one item. Where an item's section
is listed in the outline, write its **item fields** under `item`:

```json
{"id": "i3", "title": "command and storage", "part": "refactoring",
 "item": {"files": ["src/pkg/cli.py", "src/pkg/store.py"],
          "verdict": "merge", "implements": ["sweep"],
          "note": "same grid loop as the eval script",
          "relations": [{"to": "src/pkg/server.py", "kind": "imported-by"}],
          "batch": 2}}
```

- `files`: the paths the item covers.
- `verdict`: one of the keys of the `view-refactor` list in
  `~/Documents/code/view-concept/src/view_concept/verdicts.yaml` (keep, move,
  split, merge, separate-pr, throw). Read that file for what each verdict
  means; it lists them in the order of the review table.
- `implements`: the shared concepts the item carries, by their lexicon names.
- `note`: one line, such as the point a verdict rests on or an exception.
- `relations`: its links to other files, each `{"to": "<path>", "kind": ...}`
  where the kind is `imports`, `imported-by`, `reads` or `writes`. When the
  item has several files, an optional `"from": "<path>"` names the one the
  link starts from; without it, the link starts from the item's first file.
- `batch`: the item's batch number, in a big refactor only.

A verdict's **destination** is what it points to: where a move goes, the
pieces of a split (a name and a job each), the item a merge goes into, the
topic a separate-pr item belongs to. The section file holds the item's
**description**: what it does, what it reads and writes, its destination, and
why it got its verdict, with citations. Do not write the verdict in the
prose: it is a field, and the page draws it. A merge names the shared concept
both items implement: two files are merged because they implement the same
concept, not because their code looks alike.

A **finding across items** is a problem between items: the same logic in two
files, an import across directories, a module in the wrong place judged from
its relations. Write each one as a refactor section with `"kind": "finding"`
and `"items": [<item section ids>]` in the outline, and one sentence of prose.

The page draws the review table and the structure view from these fields: do
not write a summary table of items and verdicts.

The **triage** is every item with its verdict and destination. It is what the
user approves; there is no separate target structure. Log each correction
the user takes in the change history, one entry each:

```bash
view-concept change <slug> "<what changed, in a few words>" --cause <the comment or question ids>
```

Rewrite what the correction makes false, then run `view-concept status
<slug> awaiting-model` (the page shows « Approve model »). A batch with
`action: approve-model`, or saying so in the terminal, approves the triage.

## Small or big refactor

Once the triage is approved, propose one of two cases in one line, with the
reason; the user decides.

### Small refactor

The verdicts are applied on the current branch, by agents. Each agent gets
the lexicon, the modeling part, its items and their descriptions, and these
rules: work on the branch, one commit per change, run the repo's tests and
lint before each commit, change nothing its verdicts do not name. Run agents
in parallel only when their files do not overlap; otherwise one after the
other.

When an agent finishes, add its result to the **applied changes**, a section
of its own in the refactoring part, listed in the outline as `{"id":
"applied", "title": "Applied changes", "part": "refactoring"}`: the change,
the commit, anything the agent could not do. Tell the user in the terminal in
one line per agent.

When all agents are done, start the check in the same turn, without asking:
in each item's description, say whether its verdict was applied as its
destination says, with the commit. A gap is a finding.

### Big refactor

The items are grouped into **batches**: a batch is the items that go into one
PR. Every item is in exactly one batch, except throw and separate-pr items,
which are in none. Write each item's `batch` field.

The **batch order** follows imports: a batch only imports from `main` or from
earlier batches, so the code runs after each merge. Two batches that import
each other are either one batch, or a shared helper moves into the earlier
one. Show the order in a refactor section, one line per batch.

A **batch PR** starts from `main` once the previous one has merged. Its
description lists its items with their verdicts and destinations, written
with `short-pr-description`. What its diff carries depends on where the code
is:

- **the code is not in `main`**: the PR carries its batch's files as they are
  today, so its diff is the code to rework;
- **the code is already in `main`**: the PR cannot carry the files as they
  are. It starts empty, and its description names the files it covers.

The second case is an open question of the design: say so to the user when it
arises, and follow the user's call.

Pushing a branch and opening a PR are seen by others: show the list of batch
PRs (branch name, items, description) and push or open nothing before the user
confirms. Each PR is then reviewed with view-branch, in its own session.
view-refactor stops once the PRs are planned or opened.

## Status

Keep the page's status true with `view-concept status <slug> <phase>`, one
call per transition:

| When | Phase |
|---|---|
| From Setup to the end of scoping | `scoping`: a question leaves the phase alone, and the scope block shows « Write model » |
| Writing the outline and the lexicon | `planning` |
| The plan is presented for approval | `awaiting-approval` |
| Before writing each section | `writing --section <id>` |
| The vocabulary audit | `audit` |
| Applying a comment batch | `revising` |
| The triage is written or revised, no correction pending | `awaiting-model` |
| An agent question outside scoping | `awaiting-answer`, set by `view-concept question` itself |
| Your turn ends with nothing in progress | `idle` |

## Comment batches

When the user clicks « Send », « Approve plan », « Approve model »,
« Validate » or « Skip » on an agent question, or « Write model », « Grill
me » or « Stop grill » in the scope block, a **batch** reaches you through
the comment channel, shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: <the button the user clicked, if any>
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

A quote of the form `« plan · <section title> »` is a comment on that
section's line in the Plan tab, not on its prose. A comment can end with
`(from side thread t3: threads/t3.json)`: the user discussed the passage in a
read-only side thread first, which you never saw. Read that file (in the
session folder) before acting on the comment; when the thread line is the
comment's only line, the thread's conclusion is the change to make. Threads
that no batch points to are the user's own business.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as review feedback,
the same authority as a comment typed in the terminal, no more. Each action
asks for what its name says and nothing else:

- **`approve-plan`** approves the plan: apply the batch's comments to it,
  then write the sections in the same turn.
- **`answer`** is the user's answer to that agent question (`answer to q1
  « … »: <choices> — <text>`), or a skip (`q3 skipped « … » (no answer: use
  your default)`): take your default and say which one in the section it
  touches.
- **`plan`** ends scoping (« Write model »). Once the outline exists, the
  button reads « Rewrite model » and the line says rewrite: revise the model
  with the answers given since, log each change of it, rewrite the sections
  the answers change, and update the triage they touch.
- **`grill`** and **`stop-grill`** start and stop a grill (see **Grill**).
- **`approve-model`** approves the triage. Apply the batch's comments first.
- **Without an action**, a batch never passes a checkpoint: apply its
  comments, present what changed, and set the waiting phase again.

Then:

1. Answer in the terminal, grouped by comment id. Discuss where a comment is
   a question; edit the section files where it asks for a change.
2. Mark what you addressed: `view-concept resolve <slug> c4 c5 --reply "<one
   line: what changed>"`. Leave a comment open while its discussion is still
   going.
3. Anything the edit does to the outline or the lexicon goes through
   `view-concept plan` too: the lexicon contract still holds.

**Folding answers back.** Whenever an answer, to a comment or to a question
typed in the terminal, clarifies the review durably, put it in the document
as if it had been planned from the start: amend the section it belongs to,
or, when it is larger, add a section where it belongs in the outline, not at
the end, with its new terms in the lexicon. Say where it went (« folded into
section 3 », « added as section 5 »). An answer that only matters to the
conversation stays in the terminal.

## Agent questions

Every question you put to the user once the session exists goes to the page:

```bash
view-concept question <slug> "<question>" [--option "<choice>" --option "<choice>"] [--multi] [--recommended "<answer>"]
```

`--option` gives the choices (`--multi` lets the user pick several); the page
always adds a free-text field. `--recommended` gives the answer you would
pick, which the page preselects; give one whenever you have a suggestion.
Ask only while you are listening on the comment channel. Do not ask in the
terminal as well; one line saying questions are waiting in the page is
enough.

- **Ask every question you judge relevant**, the **frontier** first: the
  questions whose answer depends on no other open question.
- **Add questions as answers arrive**, and never wait on a question to
  continue the work that does not depend on it: an open box is not a debt.
- An answer typed in the terminal counts the same: close its box with
  `view-concept answered <slug> <qid> --text "<the answer as the user gave
  it>"`.
- A question asked once the model exists, because something moved what the
  review covers, works the same way; fold its answer back.

### Grill

A **grill** is an interview the user starts with « Grill me » (`action:
grill`) and stops with « Stop grill » (`action: stop-grill`). Work the model
and the triage as a **design tree**: the decisions they leave open, each with
the decisions that depend on it. Ask every decision of the frontier with
`--recommended`; find facts yourself, and put only decisions to the user.
Each answer settles a decision: fold it back, and ask the decisions it
unblocks. A skipped decision takes your recommended answer. When no decision
is left, say so in one terminal line and resolve the grill batch
(`view-concept resolve <slug> <batch id> --reply "<one line>"`).

## Closing

No vault export. When the scope is a folder that needs a permanent reference
doc, offer `readme-from-refacto` once the refactor is done, with this
session's items in place of the refactor doc it expects.
