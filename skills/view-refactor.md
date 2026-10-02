---
name: view-refactor
description: >-
  Review a part of the codebase that was written quickly in the view-concept
  page, decide what stays, and restructure it: map the scope, give each item a
  triage verdict and its destination, have the user approve the triage, then
  either apply it on the current branch or split the work into batch PRs that
  view-branch takes over. Uses view-concept. Use when the user wants to clean
  up, triage or restructure vibe-coded or experimental code — "help me decide
  what to keep in X", "triage this folder", "clean up X before I PR it",
  "refactor this module", invokes /view-refactor.
argument-hint: "[the files or folder to review]"
---

# /view-refactor

Runs **`view-concept`** (`~/.claude/commands/view-concept.md`, which runs
`explain-concept` in the page) on existing code, and adds what a refactor
needs around it: a triage of the code, agents or PRs that apply it, and a
check of the result. Read view-concept and follow it, with what is below. It
borrows view-branch's mechanics (`~/.claude/commands/view-branch.md`) where
this file says so; read the parts it names.

<subject> #$ARGUMENTS </subject>

## Bindings

- **Session**: a code session opened on the current branch,
  `view-concept new ... --kind code --repo <repo root> --workflow view-refactor`.
  The workflow makes the page use view-refactor's verdicts. Citations are
  required, as view-concept says.
- **Level**: the user owns the repository. Skip the level question.
- **Goal**: decide what stays, and restructure it. Skip the goal question.
- **Phase 3 (calibrate)**: skip.

## Scope

The **scope** is the files the user points at (a folder, a module, a list of
scripts), plus one sentence on what is not reviewed: sibling folders, shared
libraries the scope imports, callers outside it. Ask for the scope when the
argument does not give it. Write the boundary sentence in the proposal section
of Part 1.

## Before Phase 2 — ground it

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

## Part 1 — what the scope is

The Phase 2 outline starts with this fixed skeleton, in this order:

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

Each section gives its core in eight lines of prose or fewer, in full
sentences, never in bullet fragments; a table or a diagram replaces prose
where it can. Count the lines before showing Part 1, as view-branch says.

## The triage — Part 2

An **item** is cut as in view-branch: one script, or several files that share
one job you can name. Every file of the scope belongs to exactly one item.
Each item is a refactor section (`"part": 2`) with its item fields under
`item`, in the format view-branch gives:

- `files`, `note` and `relations`, as in view-branch;
- `verdict`: one of the keys of the `view-refactor` list in
  `~/Documents/code/view-concept/src/view_concept/verdicts.yaml` (keep, move,
  split, merge, separate-pr, throw). Read that file for what each verdict
  means; it lists them in the order of the review table;
- `implements`: the shared concepts the item carries, by their lexicon names;
- `batch`: the item's batch number, in a big refactor only.

A verdict's **destination** is what it points to: where a move goes, the
pieces of a split (a name and a job each), the item a merge goes into, the
topic a separate-pr item belongs to. Write it in the item's description, with
what the item does, what it reads and writes, and why it got its verdict. A
merge names the shared concept both items implement: two files are merged
because they implement the same concept, not because their code looks alike.

Findings across items are written as in view-branch.

The **triage** is every item with its verdict and destination. It is what the
user approves; there is no separate target structure. Use view-branch's
approval mechanism: record each correction the user takes with
`view-concept change`, rewrite what it makes false, then run
`view-concept status <slug> awaiting-model`. A batch with
`action: approve-model`, or saying so in the terminal, approves the triage.

## Small or big refactor

Once the triage is approved, propose one of two cases in one line, with the
reason; the user decides.

### Small refactor

The verdicts are applied on the current branch. Send agents under
view-branch's agent rules: work on the branch, one commit per change, run the
repo's tests and lint before each commit, change nothing the verdicts do not
name. Each agent gets the lexicon, Part 1, its items and their descriptions.
Report each result in the applied changes (the Part 2 section `applied`), as
view-branch does. When all agents are done, start the check in the same
turn, without asking: go through the items in the refactor tab:
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
confirms. view-branch is then run on each PR, in its own session.
view-refactor stops once the PRs are planned or opened.

## Closing

No vault export. When the scope is a folder that needs a permanent reference
doc, offer `readme-from-refacto` once the refactor is done, with this
session's items in place of the refactor doc it expects.
