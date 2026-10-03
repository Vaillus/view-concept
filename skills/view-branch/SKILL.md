---
name: view-branch
description: >-
  Work on a branch in the view-concept page, concepts first: build the model
  of what the branch introduces and how it fits the existing code, challenge
  and revise it with the user, send agents to bring the code in line with the
  revised model, then check the code item by item against it. Uses
  view-concept. Use when the user wants to work on, understand or rework a
  branch they are building — "let's work on this branch", "review my branch",
  "explain this branch so I can decide what stays", invokes /view-branch.
argument-hint: "[the branch or PR number]"
---

# /view-branch

Runs **`view-concept`** (the `view-concept` skill, which runs
`explain-concept` in the page) on a branch, and adds what a review needs
around it: a model of the branch, agents that change the code, and a check of the
code against the model. Read view-concept and follow it, with what is below.

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

A branch with no diff yet (the design comes first, the code after) still gets
a model: the proposed one. Say so in the proposal section of Part 1, and mark
each concept you propose yourself, as opposed to one the user asked for, so
the user reads Part 1 as a proposal to approve, not a description to check.

In the page, the model is the lexicon of `plan.json` (one entry per concept,
`definition` + `tip`) and Part 1 of the explanation. A **model change** is one
correction the user takes or agrees to during Part 1: a concept renamed,
merged, split, added, removed, or one of its rules changed. Record each one at
once, in one sentence that an agent could act on:

```bash
view-concept change <slug> "<the change>" --why "<reason>" --instead "<what the branch does now>" --files <paths it touches>
```

Record only changes the user took or agreed to, never your own suggestion.
Then rewrite the sections and lexicon entries the change makes false: the page
always shows the model as it now stands, not as the branch wrote it.

## Bindings

- **Session**: a code session, `--kind code --repo <repo root> --workflow view-branch`, opened on the
  branch. Citations are required, as view-concept says.
- **Level**: the user owns the repository. Skip the level question.
- **Goal**: decide what the branch should be, and get it there. Skip the goal
  question.
- **Phase 3 (calibrate)**: skip.

## Before Phase 2 — ground it

Read, in this order:

1. the repo's docs: README files, a `docs/` folder, module docstrings that
   describe concepts. The model starts from the concepts they already define;
   Part 1 then covers only what the branch adds or changes;
2. the PR description (`gh pr view <n>`), and the commits (`git log <base>..HEAD`);
3. the diff (`git diff <base>...HEAD`);
4. the existing code the branch touches or calls: the modules it extends, their
   callers, their tests. Part 1 is about how the branch fits *this*, so you must
   know it before outlining.

Note what the diff does that the description does not mention, and the
reverse. Both are findings. So is a doc that is missing or that the code
contradicts: it is a gap, and you rebuild the concept from the code.

## The flow

The review runs in three steps: **model consolidation** (the model is written
and corrected with the user), **model matching** (agents change the code to
match it) and **refactoring** (the code is checked against it, item by item).
Model consolidation is explain-concept's workflow on Part 1 only; model
matching and refactoring come after it.

A review is a list of **sections**: plan.json lists them under its `outline`
key, and `sections/<id>.md` holds the text of each. A section with
`"part": 2` is a **refactor section**: the page shows it in the refactor tab,
not in the Model tab (the page's name for the Explanation tab in a branch
review).

### Model consolidation (Part 1)

The Phase 2 outline is this fixed skeleton:

1. **Today.** What the user works with before the branch, shown on a real
   example: an existing session, a real file, a command and its output. No
   new concept yet; only the vocabulary the code already has.
2. **What goes wrong.** The problems the example shows, in the user's terms:
   what they cannot do, what breaks, what is confusing. Each concept later in
   Part 1 answers one of them; a concept that answers none is a finding.
3. **The proposal.** What the branch changes, shown on the same example after the
   change: a mockup of the page or the output, or a before/after Mermaid
   diagram. Say what the branch does not do. When the branch has no diff yet,
   say here that the model is a proposal.
4. **One section per concept** it introduces or changes: what it is, its
   rules, where it is implemented (cited). Concepts in the order they depend
   on each other, starting from the one the others are defined by. Names
   that clash with existing ones are said here.

The order is fixed: the user reads the concepts after seeing what they are
for. A concept-first Part 1, with no picture of the result, was too abstract
to discuss.

Write only these sections in Phase 5, then run the Phase 6 audit on them: the
vocabulary of the model is what the agents and the code will inherit.

**Keep Part 1 short.** It is read to discuss the concepts, not to check them:
each section gives the core in a few lines (three to eight), a table or a
diagram where it replaces prose. Details go to Part 2, or to a new section
placed where it belongs when the user asks for one (a folded answer, as
view-concept says). A first version of Part 1 written at full
explanation depth was judged far too long to read at this stage.

**Check the length before showing it.** After writing Part 1, and again after
each revision, count the lines of prose in every section (tables, code blocks
and diagrams don't count). Cut any section over eight lines before you tell
the user it is written or set `awaiting-model`. When the user is confused,
make the order clearer or add a picture: more prose is not the answer.

Then the discussion: the user challenges the model, in the page or in the
terminal. Record each model change as above. When no correction is pending,
run `view-concept status <slug> awaiting-model`: the page shows « Approve
model ».

Model consolidation ends when the user approves the model: a batch with
`action: approve-model`, or saying so in the terminal. Approving the model
also means « start the implementation »: apply the batch's comments to the
model first, then go to model matching in the same turn, without asking
again.

### Model matching — the agents

Compare the whole model with the code, not only the recorded changes: a
concept the branch announces but half implements, or a rule the code contradicts,
is a gap even if nobody corrected it. List the gaps in the terminal, one line
each.

Then close them, split as you judge best: one agent or several. Say in one
line how you split the work; do not wait for a go, the model approval was it.

Each agent gets the whole model (the lexicon and Part 1 as they now stand),
the list of model changes (what moved since the branch as written), its gaps, the
files, and these rules: work on the branch, one commit per change, run the
repo's tests and lint before committing, do not change anything its gaps do
not name. Run agents in parallel only when their files do not overlap;
otherwise one after the other.

When an agent finishes, add its result to the **applied changes**, its own
Part 2 section, listed in plan.json as
`{"id": "applied", "title": "Applied changes", "part": 2}`: the change, the
commit, anything the agent could not do.
Tell the user in the terminal in one line per agent.

When all agents are done and the applied changes are up to date, start
refactoring in the same turn, without asking: the user reads the commits
alongside Part 2.

### Refactoring — the code (Part 2)

Append Part 2 to the outline, after Part 1. Every section of Part 2 is a
refactor section, so the page shows it in the refactor tab. Part 2 holds one
section per item, the findings across items, and the applied changes.

An **item** is one unit of the diff that gets its own verdict: one file, or
several files that share one job you can name (« command and storage »).
Every changed file belongs to exactly one item, the docs and the tests
included. Each item is its own refactor section.

Where an item's section is listed in plan.json, write its **item fields**
under `item`:

```json
{"id": "i3", "title": "command and storage", "part": 2,
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

Once Part 2 is written, and again after each revision of it when no
correction is pending, run `view-concept status <slug> awaiting-pr`: the page
shows « Create PR » at the bottom of the refactor tab.

## Closing

Closing starts when the user asks for the PR: a batch with
`action: create-pr`, or saying so in the terminal. Apply the batch's comments
first: a comment that corrects the model is a model change, so record it and
go back to model consolidation or model matching for it. Then close in the
same turn, without asking again: the click was the go.

First send one agent to update the repo's docs from the model: the concepts
and their rules as they now stand, without the before/after comparison that
Part 1 makes. One commit on the branch, under the agent rules of model
matching.

Then write the PR description with `short-pr-description`, using the model
changes as its Decisions. Push the branch and open the PR with
`gh pr create --body-file <file>`, or, when the branch already has one,
update it with `gh pr edit <n> --body-file <file>`. Give the PR link in the
terminal: the user reviews it in VS Code. No vault export.
