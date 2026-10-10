# Planning rules

The rules every agent that changes the outline or the lexicon of a branch
review follows: the planner during scoping, the writer after « Write model ».
Your role file says when you apply them.

## The model

The **model** of a branch is the set of concepts it introduces or changes. A
**concept** is an object, a rule, a format or a name the code relies on: « a
gate drops a segment when its silence ratio exceeds the threshold ». A UI
element, a file, a function or a table row is not a concept: it is where a
concept is implemented. Name the concept, and cite the part.

The model starts from the concepts the repo's docs already define; the
modeling part covers only what the branch adds or changes.

A branch with no diff yet (the design comes first, the code after) still gets
a model: the proposed one. Say so in the proposal section, and mark each
concept you propose yourself, as opposed to one the user asked for, so the
user reads the modeling part as a proposal to approve, not a description to
check.

## Writing the outline and the lexicon

Never edit `plan.json` by hand: it holds the initial request, the base branch
and the workflow too, and one bad rewrite loses them. Write the outline, the
lexicon or both with

```bash
view-concept plan <slug> <file>    # or - to read stdin
```

where the file is `{"outline": [...], "lexicon": [...]}`, either key alone
when only one changes. Each key replaces the whole list: start from the
current one (`plan.json`, or the context) and change what you mean to. The
command refuses an outline entry without an id or a title, a repeated id, and
a lexicon entry whose section is not in the outline.

## The outline

The outline (`outline` in `plan.json`, one entry `{"id", "title", "earns"}`
per section, `earns` saying what the section gives the reader) follows this
fixed skeleton:

1. **Today.** What the user works with before the branch, shown on a real
   example: an existing session, a real file, a command and its output. No
   new concept yet; only the vocabulary the code already has.
2. **What goes wrong.** The problems the example shows, in the user's terms:
   what they cannot do, what breaks, what is confusing. Each concept later
   answers one of them; a concept that answers none is a finding.
3. **The proposal.** What the branch changes, shown on the same example after
   the change: a mockup of the page or the output, or a before/after Mermaid
   diagram. Say what the branch does not do. When the branch has no diff yet,
   say here that the model is a proposal.
4. **One section per concept** it introduces or changes: what it is, its
   rules, where it is implemented. Concepts in the order they depend on each
   other, starting from the one the others are defined by. Names that clash
   with existing ones are said here.

The order is fixed: the user reads the concepts after seeing what they are
for. A concept-first modeling part, with no picture of the result, was too
abstract to discuss.

Section ids are stable: when you reorder, keep each section's id and change
its position. The page anchors the user's comments to ids.

## The lexicon

One entry per concept in `lexicon` of `plan.json`:
`{"term", "section", "definition", "tip"}`, where `section` is the term's
**home section**, the one that introduces it. The `definition` is one line;
the `tip` (written with the section's prose, by the writer) is the hover text.
Write both for someone who has read the sections in order up to the home
section and nothing after.

**The precedence rule.** Every text about a term (its introducing prose, its
`definition`, its `tip`) uses only terms whose home section is at or before
its own. When it needs a later term, reorder the outline or say the idea in
plain words; never point ahead. A **forward reference** is a `definition` or
`tip` that uses a later term; an **early use** is a term that appears in a
section placed before its home section. `view-concept check <slug>` lists
both.

No location details in a `definition` or a `tip` (a file, a key, a section
number): those go in the home section's prose, as citations. A `tip` does not
repeat what other entries define.

## The change history

Log every change of the model at once, one entry each:

```bash
view-concept change <slug> "<what changed, in a few words>" --by <planner|writer> --cause <ids>
```

A change of the model is a concept added, removed, renamed, merged or split, a
rule or a relation changed, a section added, moved or removed. A wording fix
that leaves the model as it was gets none. Say the change in a few words
(« gate split into silence gate and length gate »), longer only when the
change itself is large. No implementation details: no files, no « what the
branch does now ». `--cause` gives the ids of the events that led to it
(questions `q3`, comments `c7`, terminal messages `tm2`); leave it out for a
change you make on your own judgment.

## Questions to the user

Every question you put to the user goes to the page:

```bash
view-concept question <slug> "<question>" [--option "<choice>" ...] [--multi] [--recommended "<answer>"]
```

Never ask in the terminal: you do not have one. The user owns the
repository, and the goal is fixed (decide what the branch should be, and get
it there): never ask their level, their goal, or whether they know a
prerequisite. Ask every question you judge
relevant, the frontier first (those whose answer depends on no other open
question), each with `--recommended` when you have a suggestion. A question
the code, the session files or a command can answer is not a question for the
user: look it up. Never ask again a question the context lists, open, answered
or skipped. A skipped question means: use your default.

During a grill (the context says « A grill is running »), work the outline as
a design tree: ask every decision whose prerequisites are settled, each with
its recommended answer. When no decision is left, say so in your report.
