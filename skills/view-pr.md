---
name: view-pr
description: >-
  Review a pull request in the view-concept page, concepts first: build the
  model of what the PR introduces and how it fits the existing code, challenge
  and revise it with the user, send agents to bring the code in line with the
  revised model, then check the code item by item against it. Uses
  view-concept. Use when the user wants to review, understand or rework a PR
  or a branch — "review PR #49", "explain this PR so I can decide what stays",
  "let's work on this branch", invokes /view-pr.
argument-hint: "[the PR number or branch]"
---

# /view-pr

Runs **`view-concept`** (`~/.claude/commands/view-concept.md`, which runs
`explain-concept` in the page) on a pull request, and adds what a review needs
around it: a model of the PR, agents that change the code, and a check of the
code against the model. Read view-concept and follow it, with what is below.

The tool is self-contained: the model is built for this PR and lives in the
session; it reaches the repository only through the docs update at closing.

<subject> #$ARGUMENTS </subject>

## The model

The **model** of a PR is the set of concepts it introduces or changes. A
**concept** is an object, a rule, a format or a name the code relies on: « a
cohort is the group of speakers a recording comes from », « a gate drops a
segment when its silence ratio exceeds the threshold », « `prepared/` holds one
folder per dataset ». For each concept, the model says what it is, the rules it
obeys, and how it relates to the concepts that existed before the PR.

A UI element, a file, a function or a table row is not a concept: it is where
a concept is implemented. « a row of the review table » is a part of a page;
the concept behind it is what the row stands for (« an item is one unit of the
diff that gets a verdict »). Name the concept, and cite the part.

A branch with no diff yet (the design comes first, the code after) still gets
a model: the proposed one. Say so in the first section of Part 1, and mark
each concept you propose yourself, as opposed to one the user asked for, so
the user reads Part 1 as a proposal to approve, not a description to check.

In the page, the model is the lexicon of `plan.json` (one entry per concept,
`definition` + `tip`) and Part 1 of the explanation. A **model change** is one
correction the user takes or agrees to during Part 1: a concept renamed,
merged, split, added, removed, or one of its rules changed. Record each one at
once, in one sentence that an agent could act on:

```bash
view-concept change <slug> "<the change>" --why "<reason>" --instead "<what the PR does now>" --files <paths it touches>
```

Record only changes the user took or agreed to, never your own suggestion.
Then rewrite the sections and lexicon entries the change makes false: the page
always shows the model as it now stands, not as the PR wrote it.

## Bindings

- **Session**: a code session, `--kind code --repo <repo root>`, opened on the
  PR branch. Citations are required, as view-concept says.
- **Level**: the user owns the repository. Skip the level question.
- **Goal**: decide what the PR should be, and get it there. Skip the goal
  question.
- **Phase 3 (calibrate)**: skip.

## Before Phase 2 — ground it

Read, in this order:

1. the repo's docs: README files, a `docs/` folder, module docstrings that
   describe concepts. The model starts from the concepts they already define;
   Part 1 then covers only what the PR adds or changes;
2. the PR description (`gh pr view <n>`), and the commits (`git log <base>..HEAD`);
3. the diff (`git diff <base>...HEAD`);
4. the existing code the PR touches or calls: the modules it extends, their
   callers, their tests. Part 1 is about how the PR fits *this*, so you must
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
not in the Explanation tab.

### Model consolidation (Part 1)

The Phase 2 outline is this fixed skeleton:

1. **What the PR does, and what it does not.** One paragraph, and the
   boundary.
2. **The problem it solves.** The job the PR does for its user, or the
   questions it lets them answer, in the user's terms and before any concept.
   Each concept in the next sections serves part of this job; a concept that
   serves none is a finding.
3. **One section per concept** it introduces or changes: what it is, its
   rules, where it is implemented (cited). Concepts in the order they depend
   on each other, starting from the one the others are defined by.
4. **How the concepts fit the existing code.** What existed before; what each
   new concept replaces, extends or duplicates; names that clash with existing
   ones. A Mermaid diagram, before and after.

Write only these sections in Phase 5, then run the Phase 6 audit on them: the
vocabulary of the model is what the agents and the code will inherit.

**Keep Part 1 short.** It is read to discuss the concepts, not to check them:
each section gives the core in a few lines (three to eight), a table or a
diagram where it replaces prose. Details go to Part 2, or to a question
section when the user asks for one. A first version of Part 1 written at full
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
concept the PR announces but half implements, or a rule the code contradicts,
is a gap even if nobody corrected it. List the gaps in the terminal, one line
each.

Then close them, split as you judge best: one agent or several. Say in one
line how you split the work; do not wait for a go, the model approval was it.

Each agent gets the whole model (the lexicon and Part 1 as they now stand),
the list of model changes (what moved since the PR as written), its gaps, the
files, and these rules: work on the PR branch, one commit per change, run the
repo's tests and lint before committing, do not change anything its gaps do
not name. Run agents in parallel only when their files do not overlap;
otherwise one after the other.

When an agent finishes, add its result to a question section `q-applied`
(« Changes applied to the code »), with `"part": 2` where the section is
listed in plan.json: the change, the commit, anything the agent could not do.
Tell the user in the terminal in one line per agent.

When all agents are done and `q-applied` is up to date, run
`view-concept status <slug> awaiting-review`: the page shows « Review code »
at the bottom of the Explanation tab, so the user can look at the commits
first.

Refactoring starts when the user asks for it: a batch with
`action: review-code`, or saying so in the terminal. Apply the batch's
comments first: a comment that corrects the model is a model change, so
record it and go back to model consolidation or model matching for it. Then
start refactoring in the same turn, without asking again.

### Refactoring — the code (Part 2)

Append Part 2 to the outline, after Part 1. Every section of Part 2 is a
refactor section, so the page shows it in the refactor tab. Part 2 holds one
section per item, the findings across items, and `q-applied`.

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
- `verdict`: one of the values below.
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

The verdict is one of these keys:

- `conforms`: matches the model.
- `diverges`: does not match the model; say how in the description. Goes
  back to model matching.
- `out-of-pr`: belongs in another branch.
- `throw`: nothing needs it.
- `split`: does several jobs; list the pieces in the description.
- `move`: in the wrong place; say where it belongs. Goes back to model
  matching, where an agent moves it.

A **finding across items** is a problem between items: the same logic in two
files, an import across directories, a module in the wrong place judged from
its relations. Write each one as a refactor section with `"kind": "finding"`
and `"items": [<item section ids>]` in plan.json, and one sentence of prose.

The page draws the review table and the structure view from these fields:
do not write a summary table of items and verdicts.

Code that does something no concept describes means the model has a gap: go
back to model consolidation for that concept.

## Closing

When the user is done, first send one agent to update the repo's docs from
the model: the concepts and their rules as they now stand, without the
before/after comparison that Part 1 makes. One commit in the PR, under the
agent rules of model matching.

Then write the PR description with `short-pr-description`, using the model
changes as its Decisions. Show it, and run `gh pr edit <n> --body-file <file>`
only once the user approves it. No vault export.
