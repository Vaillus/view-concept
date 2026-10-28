---
name: document-feature
description: >-
  Carry the model of the feature in progress into the repo's READMEs once
  the code carries it, by three decisions taken in order: IF a concept of
  the model enters the docs (the concept triage), WHERE it goes (the folder
  model of the README whose folder writes it, beside write-readme's parts),
  and HOW the README changes (a local model edit, or a restructuring whose
  move plan the user corrects before any folder model is written). The
  code is the source of truth. Runs after write-readme, whose parts of
  each README it reads by their headings. Use when a feature's doc pass writes the
  folder models of its READMEs — "document the feature", "carry the model
  into the READMEs", invokes /document-feature.
argument-hint: "[the session folder or slug] [the READMEs: default, every README of the doc set]"
---

# /document-feature

Carries the **model** of the feature in progress (the concepts its branch
introduces or changes, with their rules, written in the sections of its
session) into the repo's `README.md` files. The request names the session
(`~/.view-concept/sessions/<slug>/`) and, optionally, the READMEs to work
on; by default, every `README.md` of the session's doc set (`view-concept
doc-set <slug>`). With no session named, stop: the skill has no model to
carry.

In a feature's doc pass, the skill runs once on the READMEs of the doc set,
after write-readme has written its own parts of each README, from the code:
a README that was missing has its draft, a README write-readme found
untitled has its parts under their headings, and the README of a folder
the branch removes is retitled, nothing else (see **Sharing a README with
write-readme**). You create no README. The request may also carry the
user's comments to apply, each with its id, its quote and its text: on a
README's folder model (`(doc <path>)`), on a row of the concept triage
(`(triage <id>)`) or on a row of a move plan (`(moves <readme> · passage
<id>)`), or a missing fact to take back (see **Comments**).

**Input**: the session's model (its `sections/`, the outline and the
`lexicon` of its `plan.json`, `change-history.json`, `code-map.md`) and the
**diff**, the branch's changes against its base (`git diff <base>...HEAD`,
the base in `plan.json`).

**The code is the source of truth.** A README tells an agent where to look
and why; the agent checks in the code. Every fact you write is checked in
the code first: a rule the model states and the code applies otherwise is
written as the code has it, and goes in the run report. The README holds
this role because it sits next to the code, in front of whoever changes
the folder, with or without this tool.

The run takes three decisions, in this order, for the whole model first and
then README by README:

1. **IF**: which concepts of the model enter the docs (**The concept
   triage**).
2. **WHERE**: in which README each goes, and in which part of it (**Where a
   concept goes**, **Sharing a README with write-readme**).
3. **HOW**: what changes in each README: a **local model edit** or a
   **restructuring** (**How a README changes**).

The rules below are principles, each with cases to recognise it. The cases
are examples, not a closed list: judge each README yourself, with no
threshold, and say what you decided in the run report. The user corrects a
decision by a comment.

The running example is benchmark-package, a branch of an audio repo that
moves `experiments/benchmark/` up to `benchmark/`, gives it a public API
(`load_dataset` and `score`), and gives the WER of a set of clips one
definition, the **pooled WER**, in `core/transcript/`, which the benchmark,
the fine-tunings and the studies call.

## Reader and lexicons

The **repo lexicon** is `.agents/lexicon.md` at the repo root, read by the
agents that write the docs; no README links to it:

```md
# <repo name>

## Reader
Knows speech processing and ASR evaluation (VAD, transcription, WER);
has never opened this repo.

## Terms

**Gate**:
A rule fitted per model that deletes a transcribed segment likely to be made up by the model.
```

The **reader** of a doc is the one it is written for, with what they
already know; a doc has one. The **reader line** (`## Reader`) is the field
that reader knows, and that they have never opened this repo. A **folder
lexicon** is the same file in a folder below the root, for the terms only
the folders under it share. Read the repo lexicon, then each folder lexicon
down to the README's folder; where two disagree (reader line or a term),
the closest wins. A lexicon outside the README's path is not read for it.
Never edit a lexicon: the doc pass writes them.

The reader line sorts the terms a folder model uses:

- a **field term** is one anyone in the reader's field knows: use it bare
  (the folder model of `core/transcript/` does not say what a WER is, only
  what the repo does with it);
- a **repo term** exists only in this repo: define it in a clause where the
  reader first needs it, in a lexicon entry's words, word for word, when
  one has it; else under the name and in the words of the session's
  lexicon. A repo term several folders use that no lexicon on the path has
  is a **candidate**: list it in the run report.

## The inclusion test

Every sentence you write in a folder model stays only if:

1. the reader needs it to use or change what the README covers;
2. no other doc file already says it. Another passage of the same README
   does not count.

A sentence that fails only the second shrinks to a few words and a link. A
rule of the folder model passes the first by construction: whoever uses
what the folder returns or exposes would get something wrong without it.

## The concept triage

The model holds concepts of unequal weight: a rule the numbers a folder
returns depend on, a setting internal to one file, an observation the code
does not apply. The **concept triage** asks each concept of the model one
question: **would whoever uses what the folder returns (a file, a number)
or exposes (the names others import from it) get something wrong without
knowing its rule?** Yes: the concept enters the docs, in a folder model.
No: it stays out of the docs, and where it goes instead is not this
skill's business.

The test counts the error, not the change:

- the pooled WER and its rule on clips without speech enter: whoever
  ignores it compares that number to a WER computed otherwise, and thinks a
  model better than it is;
- the columns of `summary.csv` enter: a study reads them by name, and
  whoever renames one breaks its figures with no error;
- the offline mode of Hugging Face, set when the harness is imported,
  stays out: a study only imports the public API, which it does not touch;
- rounding the scores of `summary.csv` from three decimals to two changes
  what the folder returns and misleads nobody: it stays out;
- an observation, or the reason for a decision (why the old WER function
  was removed), fails on its own: the code does not apply it, and nobody
  gets anything wrong by ignoring it.

Record one row per concept of the model, in the model's order, even for
the concepts that stay out (the user then sees what stays out without
looking for an absence):

```
view-concept triage <slug> set "<concept>" enters|out "<reason>"
```

`<reason>` is one line, the answer to « who ignores it would get what
wrong? ». `view-concept triage <slug>` prints the rows; `remove <id>`
drops a concept the model no longer has. The Doc tab shows the triage as a
table above the doc set. It appears with the written docs, with no stop
before writing: the user changes an answer by commenting on its row (`(triage
<id>)` in a batch). On such a comment, change the row (`set`, same concept
text, which keeps its id) and rewrite the folder models it touches.

## Where a concept goes

A concept that enters goes, **whole**, into the folder model of the README
of the folder whose files **write** it (compute it, define it, produce
it), not of the folders that call it:

- a concept only one subfolder writes goes into that subfolder's README,
  not higher;
- a **cross-cutting concept**, a rule or a format the files of several
  folders share, goes into the README of the folder whose files write it:
  the pooled WER goes into `core/transcript/README.md`, even though
  `benchmark/` calls it more than anyone. The README of a folder that calls
  it names it and links to the README that defines it, without defining it
  again; the module that computes it links there from its docstring. The
  README that defines it does not name its callers: their list changes
  while its folder does not;
- a folder that had no README has one by now, the draft write-readme
  wrote from the code: add the folder model after its parts, under a `##`
  heading of its own (`## The WER` in `core/transcript/README.md`). A
  folder whose README is not in the doc set gets none from you: name it in
  the run report (`no README:`), and the caller adds it to the doc set.

**Whole** means the objects the concept defines, the rules they follow,
their relations and what follows from them, what the code does not check
included. An isolated rule does not say what it applies to.

The triage only decides what enters. The folder model is one prose,
ordered for its reader, from all the concepts of the folder, those the
README already held and those the triage lets in: a row of the triage never
becomes a passage of its own. In `benchmark/README.md`, the public API and
the columns of `summary.csv`, two rows of the triage, make one rule: what a
study may read from the folder.

```md
## The public API

A study imports `load_dataset` and `score` (with `Dataset` and `Utterance`)
from `benchmark`, and nothing else.

- `score` gives the pooled WER of each subset, as
  [core/transcript/README.md](../core/transcript/README.md) defines it.
- `summarize` writes summary.csv, one row per model and subset. A study
  reads it by column name and imports nothing from `benchmark`: the column
  names are its whole contract with the folder.
```

Once a folder model is written, re-read each sentence against the triage: a
sentence that names a concept the triage leaves out is cut, even when it
only serves to set off another (a sentence contrasting the public API with
the offline mode of Hugging Face goes; the rule of the public API stays
alone).

A concept enters one folder model only. Another doc that already describes
it does not receive it a second time: it receives only the correction of
its sentences the code now contradicts (a doc on fine-tuning that names the
removed WER function gets that name corrected, not the pooled WER's
definition). A doc of `docs/` receives a concept only when no README can
hold it: a choice that binds several modules, with the options set aside.

## Sharing a README with write-readme

write-readme, the skill that writes a README's structure from the code,
and this skill share each README passage by passage (a **passage** is a
paragraph, a list, a table or a code block):

- **write-readme's parts**: the first sentence and the status line,
  recognised by their place at the top, untitled; the **file map** (one
  line per file or subfolder, with what it holds) under `## Files`; the
  **usage** (the folder's commands, each with what it produces) under
  `## Usage`; plus a section the repo's conventions impose, such as a
  study header (`**Status.**`, `**Data.**`, `**Result.**`). A placeholder
  left to fill (« TODO: Notion link ») or a dated migration note belongs to
  the part it sits in. A repo convention that imposes other headings for
  the file map or the usage replaces these, and the boundary is read by
  those headings.
- **The folder model**: every other passage, under any other heading. It
  gives the rules to know to use the folder without error, as the code
  applies them: the ones you write, and the ones the README already held
  before you, a caveat, a data format, links (« See also »). A **caveat** is
  a rule to know so as not to go wrong: it belongs to the folder model, and
  is yours.

write-readme, which runs on each README before you, titles its parts
`## Files` and `## Usage`, and retitles an existing README the first time
it finds it otherwise, the README of a folder the branch removes included:
on that one it only retitles, and checks and writes nothing from the
code. Read the boundary by these headings and never judge
it yourself: the untitled top and the passages under `## Files` and
`## Usage` are write-readme's, every passage under another `##` heading is
the folder model.

Neither skill touches the other's passages. You edit or write the folder
model only; a wrong path in the usage is write-readme's to correct: list it
in the run report, do not fix it. Write the folder model after
write-readme's parts, always under `##` headings of its own, neither
`## Files` nor `## Usage`: write-readme takes every passage before the
first `##` heading for its first sentence and status line, so a folder
model written there, untitled, would read as its own. A passage of the
folder model that names nothing the branch changes stays word for word,
even history or an open discussion.

## How a README changes

For each README that receives a concept, or holds a passage naming
something the branch changes, decide which change it is.

### A local model edit

A **local model edit** is a change after which each passage of the README
stays in that README, even reworded, whatever its size. Cases: a concept
renamed, split or merged without changing folder; a rule that changes
meaning; a folder model that grows more complex or simpler at once; a
folder that changes role. Most READMEs a feature touches are this case:
the READMEs of the studies that call the benchmark name it or its WER, and
none of their passages has to go elsewhere.

Judge whether the folder model **still holds**, its concepts keeping their
shape:

| The folder model | What you do |
|---|---|
| still holds | Find the passages that name what the branch changes (a concept of the model, a name the diff changes) and check each against the code. A false passage gets the smallest edit that makes it true; the others keep their text word for word. You do not re-read the passages that name nothing changed: drift older than the feature stays as it is. |
| no longer holds: the feature changes its concepts in depth, or the folder changes role | Rewrite it whole, ordered for the README's reader, from the old folder model and the concepts the triage lets in (**Where a concept goes**). Edits piled on a structure that no longer follows the concepts would grow the README by accretion. Then list its **missing facts** (below). |

A folder that changes role (a study that becomes a package others import)
also changes reader: its whole README is re-read for the new reader, and
write-readme's parts need a full rewrite by write-readme, the edit it made
before you no longer being enough. You do not write them: say it in the
run report (`role change`), and the caller starts a second write-readme
run on that README, after you, which rewrites its parts in full and copies
your folder model after them.

### A restructuring

A **restructuring** is a change after which passages must leave the
README. Cases: a folder split in two; two folders merged; a concept that
changes folder, when another folder starts writing it; a concept split
between two folders; a folder removed. In benchmark-package, the WER rules
go to `core/transcript/`: the README of `experiments/benchmark/`, which
the code moved to `benchmark/README.md`, is restructured. A README whose
folder the branch removes is always a restructuring: its write-readme run
only retitled it, with no code left to describe, so read the boundary by
its headings as for any README; its move plan says where each passage of
its folder model goes, and you delete the file once they have all gone
(step 3). write-readme's parts of it describe code the branch removes and
go nowhere.

A restructuring takes two runs, with a stop between them:

1. **The move plan.** Before writing any folder model of the run, decide
   for every README whether it is restructured, and write the **move
   plan** of each one that is: each passage of the README's folder model,
   the README it goes to, and what it becomes there, `as-is`, `rewritten`,
   or `nowhere`. write-readme's parts are not in it: the write-readme runs
   before you wrote them from each folder's code, which the plan does not
   change (the report chain and its figures, which the code moved to the
   study that draws them, are that study's usage, and its write-readme run
   wrote them there). Clear the README's old plan, then one call per
   passage, in the README's order:

   ```
   view-concept moves <slug> clear <readme>
   view-concept moves <slug> add <readme> "<passage>" --becomes as-is|rewritten|nowhere [--to <readme>] [--note "<one line>"]
   ```

   `<passage>` describes the passage in one line; `--to` is required unless
   `nowhere`, and names a README of the doc set. A README the code moved
   with its folder takes its plan at its new path, the one the doc set
   lists. Part of the plan for `benchmark/README.md`, which the code moved
   from `experiments/benchmark/`:

   | passage of the folder model | goes to | becomes |
   |---|---|---|
   | the data: a dataset's manifest, its eval subsets | `benchmark/` | as-is |
   | « clips without transcript count as hallucinations, out of the aggregated WERs » | `benchmark/` | rewritten as a link to `core/transcript/README.md` |
   | the WER over speech clips only, clips without speech, their hallucination rate | `core/transcript/` | rewritten as the pooled WER concept |
   | « a subset's own WER counts all its clips » | `core/transcript/` | rewritten: the code contradicts it |
   | results from before 30 September, « to remove after 31 October » | — | nowhere |

2. **The stop.** End the run on the plans, writing no folder model of
   the run: neither the restructured README's nor that of any README a row
   sends a passage to (its `--to`), nor that of a README whose change is a
   local model edit, even for a concept the triage puts there. Each
   README's outcome is decided (step 1), none is written. The stop holds
   only what you write: write-readme's parts stay as its runs wrote them,
   from the code, and no README is to be put back. Say in the run report
   that the move plan waits, with the READMEs it holds: every README of
   the run.
   The caller then
   puts the session in its waiting phase: a wrong destination is corrected
   on one row of the plan, before three READMEs carry it. The user comments
   on the rows (`(moves <readme> · passage <id>)` in a batch) and presses
   « Write READMEs ».
3. **The writing.** The run that follows « Write READMEs » (`action:
   write-readmes`) writes every README of the run, together: the READMEs
   the plans name from the plans and the comments on them (the passages
   each row sends, and in a destination, what the rest of this skill puts
   there: its concepts, its local model edit), and the other READMEs by
   their local model edit. You write the folder model passages, each where
   its row sends it, after write-readme's parts of its destination. A
   README the code moved with its folder is listed in the doc set at its
   new path: write its folder model there, and leave no file at the old
   path. The README of a folder the branch removes: once every passage of
   its folder model is written where its row sends it, delete the file
   (`rm`, the caller commits the deletion).

4. **The missing facts**, below, of the old folder model.

## The missing facts

After a folder model rewritten whole, or a restructuring, compare the old
folder model with what you wrote: read it fact by fact (one thing it
states: a command, a path, a rule, a reason) and keep each fact that no README you wrote says, in words or by a link to
a doc that says it. These are the **missing facts**; one said in other
words, once instead of three times, or as a link, is not missing. For
each, propose `keep` (the reader needs it; say in what form it would come
back) or `leave` (it fails the inclusion test, or the code contradicts it:
say so). The proposal drops nothing: you take none back on your own, the
user decides.

Record them on the README the old file became (its new path, in the doc
set; for a README you deleted, its own path, which the doc set keeps), with the part they come from, `model`. Clear first the README's
facts of that part alone, those of an earlier run of yours: the facts of
write-readme's parts, `readme`, stay, whichever skill ran last.

```
view-concept facts <slug> clear <path> --part model
view-concept facts <slug> add <path> "<fact>" --part model --propose keep|leave --reason "<one line>" [--passage N]
```

`--passage N` is the number of the old passage that held it, counted from
the top. From benchmark-package: « Results from before 30 September do not
compare with the new ones: the models' names and decoding changed. »

## Comments

The request may carry the user's comments, each with its id, its quote and
its text. Apply each one, and leave it open: the caller resolves it once
your work is committed.

- a comment on a passage of a README's folder model: rewrite that passage
  as the comment asks, under this skill's rules; a comment on a passage of
  write-readme's parts is not yours: name it in the run report;
- a comment on a row of the concept triage: as **The concept triage**
  says;
- a comment on a row of a move plan: it comes with « Write READMEs », as
  **A restructuring** says;
- a missing fact to take back (the user answered « reprends-le » on it):
  add it to the folder model of its README, in words or as a link to the
  doc that already says it, under the inclusion test.

## Writing

- Write in the README's language, under the session lexicon's names, the
  concepts as they now stand, without the before/after comparison the
  model makes.
- **Name the term.** Write the term itself, defined where it appears,
  never a paraphrase that takes its name later.
- **Mechanism over analogy.** A real command, file, function or flag with
  what it produces; no metaphor for a mechanism.

Once written, re-read each folder model for undefined repo terms,
metaphors, overloaded words and bare references (« the pipeline » never
introduced), and fix each: the precise term, a defining clause, or a cut.

You write the READMEs and the session files the commands above name, and
nothing else. You never commit: the caller does.

## The run report

The run's last message, one line per README, then the findings. The
first run of benchmark-package, which stops on the plan:

```
document-feature · triage: 5 enter · 4 stay out
benchmark/README.md · moved from experiments/benchmark/README.md · restructuring: move plan waiting (12 passages) · holds core/transcript/README.md, experiments/stt_benchmark_ft2/README.md, experiments/finetuning/gign/README.md
candidates: subset (benchmark/, experiments/)
code: none
```

The run after « Write READMEs »:

```
document-feature · Write READMEs
core/transcript/README.md · folder model added after the draft · 3 passages received
benchmark/README.md · moved from experiments/benchmark/README.md · role change · missing facts: 2
experiments/stt_benchmark_ft2/README.md · 1 passage received
experiments/finetuning/gign/README.md · local model edit: 1 passage edited
write-readme's parts: benchmark/README.md, usage, a path to experiments/benchmark/ (left to write-readme)
code: none
```

A README you deleted has its line too: `<path> · folder removed ·
restructuring: deleted · missing facts: <n>`.

`role change` asks the caller for a second write-readme run on that
README, a full rewrite of its parts. `no README:` names each folder a
concept goes to whose README is not in the doc set. A line `move plan waiting` asks the caller to stop until
« Write READMEs », and names after `holds` every other README of the
run (the plan's destinations and the READMEs of a local model edit),
which wait with it. `code` lists each rule of the model the code applies
otherwise, as written from the code.
