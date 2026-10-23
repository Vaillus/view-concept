---
name: write-readme
description: >-
  Write a folder's README.md from its code, or bring an existing one up to
  standard, editing only what fails and counting the passages that fail, or
  write it again from the code alone when asked and list the facts the old
  one said that the new one lost, against fixed content rules: a reader
  line and repo terms read from the repo's lexicon files, an inclusion test
  every sentence must pass, the repo's own README conventions, five parts for
  a new README, and a report printed at the end of the run.
  Use when the user wants a README written for a folder, or an existing
  README cleaned up, shortened or rewritten, notably one written by an LLM —
  "write the README of X", "rewrite this README", "clean up X/README.md",
  "this README is bloated", invokes /write-readme.
argument-hint: "[the folder, or its README.md] [rewrite] [reader: <reader line>]"
---

# /write-readme

Writes the `README.md` of one folder: the folder, or its `README.md`, is
whatever the user typed after the command name, followed by `rewrite` when
the user asks for a full rewrite (`/write-readme <folder> rewrite`). The run
reads the repo's lexicon files, the folder's code and the old README if
there is one, writes the README, and ends by printing its **run report**. It
writes no other file (except the repo lexicon when the repo has none) and
never commits.

A run has one of three outcomes:

- **draft**: the folder has no `README.md`; write one from the code, in the
  five parts;
- **edit** (always, when it has one and no full rewrite was asked for): keep
  its structure, headings and wording, change only the passages that fail a
  check, and count the **failure indicator** (see **Checking an existing
  README**);
- **full rewrite**: only on a **rewrite request**, the `rewrite` argument or
  a review's request to write a README again from scratch; write it again
  in the five parts from the code alone, without reading the old README, as
  for a draft, then list its **missing facts** (see **The missing facts**).

The run never chooses a full rewrite on its own, however much of the old
README fails: the failure indicator tells the user, who decides.

A run is **in a review** when its request names a review's session folder
(`~/.view-concept/sessions/<slug>/`): the agent of a branch review or of a
docs review ran it, and the review's page shows what the run leaves to the
user. Any other run, a `rewrite` argument typed in a terminal included, is
outside a review.

Never ask the user anything, except the one question of **The repo
lexicon** below: the reader line says who reads, the goal is always that the
reader can use or change the folder, and the inclusion test says what stays.

## The repo lexicon

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

The **reader line** (`## Reader`) is the field the reader knows. A **folder
lexicon** is the same file in a folder below the root, for the terms only
the folders under it share. Read the repo lexicon, then each folder lexicon
down to the README's folder; where two disagree (reader line or a term),
the closest wins. A `reader: <line>` in the request replaces the reader line
for this run. Never edit a lexicon that exists.

The reader line sorts the terms the README uses:

- a **field term** is one anyone in the reader's field knows: use it bare;
- a **repo term** exists only in this repo: define it in a clause where the
  reader first needs it, in a lexicon entry's words, word for word, when
  one has it, in your own otherwise. A repo term several folders use that
  no lexicon on the path has is a **candidate**: list it in the run report.

**When the repo has no lexicon**, draft one from the root `README.md`, the
root `CLAUDE.md` and the package description: the reader line those assume,
and the repo terms several folders' docs share, one line each. From the
terminal, show the draft and ask once (« Correct the reader line or the
terms, or answer « ok » »), then write it. In a review, write it without
asking.

## Sources

Every fact comes from the folder's code (always read first: modules,
commands, entry points, tests, the files it reads and writes), the old
README for an edit, the missing facts the user keeps after a full rewrite,
and the model of each session folder the request names that holds one (its
`sections/` and the `lexicon` of its `plan.json`), which holds rules the
code does not show. A branch review names its own folder; a docs review
names its own, which holds no model, and its reference model's folder when
it has one. A fact the code contradicts is written as the code has it. A term the review's lexicon has keeps its name there, and its
definition when no lexicon on the path has the term.

Before writing, read the rules the repo sets for READMEs, in the root
`CLAUDE.md` (or `AGENTS.md`) and the READMEs from the root down to the
folder (a study header, a required section). They win over this skill.

An edit keeps the old README's language; a draft and a full rewrite take
the language of the repo's other docs.

## Checking an existing README

An edit goes through the old README passage by passage (a paragraph, a
list, a table, a code block) and marks each passage that fails:

1. the inclusion test;
2. the code: a fact the code contradicts. A rule the README states that
   some code breaks (« no CLI in `core/` » while a module has one) is not
   contradicted: the passage passes, and the code is a code finding;
3. the vocabulary: a finding of the audit (see **Writing**);
4. the repo's README conventions.

Fix each failing passage where it stands and leave the others word for
word; never move, merge or retitle sections. A passage that fails only by
leaving something out (a file missing from the map) is fixed by adding the
line. A README can come out unchanged.

The **failure indicator** is the number of passages that fail a check,
counted before the edit, out of the README's passages: `3 of 6 passages
fail`. A passage that fails only by leaving something out does not count.
When the structure itself fails (a section of open discussion as large as
the rest), the indicator says so too (`structure fails`); the edit does not
fix the structure, and the run stays an edit. The indicator is in the first
line of the run report.

## The missing facts

A full rewrite never reads the old README while it writes. Once the new
README is written, compare the two: read the old README fact by fact (one
thing it states: a command, a path, a rule, a reason) and keep each fact the
new README says neither in words nor by a link to a doc that says it. These
are the **missing facts**. A fact the new README says in other words, once
instead of three times, or as a link, is not missing.

For each missing fact, give:

- the fact itself, in one sentence;
- the number of the old passage that held it, counted from the top;
- your proposal, **keep** or **leave**, with a reason in one line: keep when
  the reader needs it (and in what form it would come back: a sentence, or a
  link to the doc that says it), leave when it fails the inclusion test. A
  fact the code contradicts is listed too, proposed leave, with that reason
  (« the code contradicts it: the page opens with `view-concept open` »).

The proposal drops nothing: the new README stays as written, and the user
decides which facts come back. A fact the user keeps is added to the README
under this skill's rules, so the inclusion test can make it a link. Outside
a review, the user reads the list in the run report and names the facts to
keep in a later message; in a review, the review's agent records them in
the session and the user decides in the page. An edit has no missing facts:
the passages it changes are named in the report's `changed` line.

## The inclusion test

Every sentence of a draft, a rewrite or an edit stays only if:

1. the reader needs it to use or change this folder. A sentence that gives
   the reason the folder is built the way the reader sees it (two pairs of
   scripts, a separate archive) passes;
2. no other doc file already says it. Another passage of the same README
   does not count.

A sentence that fails only the second shrinks to a few words and a link.
Drop history and open discussions (ideas, to-dos), except history that
explains a caveat, a **placeholder** for a missing link or fact (« TODO:
Notion link », kept and listed in the report), and a dated **migration
note** on reading outputs made before a change, kept until its date.

## The five parts

A draft or a full rewrite has these parts, in this order, unless the repo's
conventions set another shape; headings are named freely.

- **Depth.** A README covers its folder at the level of its direct
  children, and says nothing about what lies inside a subfolder: that
  belongs to the subfolder's README, and what a module does to its
  docstrings. A deeper folder gets a line only when a reader would look for
  it by name (an app of its own).
- **Start minimal.** A draft starts as the first sentence and the file map.
  Add another part only when the folder has something for it the map
  cannot show.

1. **The first sentence**: the folder in one sentence, in field terms.
2. **The file map**: one line per file or subfolder that matters, with what
   it holds in a few field words, and a link to its README when it has one.
   A map line defines no repo term.
3. **The status line**: only when the folder is experimental, deprecated,
   or replaced (by what).
4. **Usage**: the folder's own commands, each with what it produces; for a
   library, one short call example per public entry point. No subsection
   per module, no list of return fields.
5. **Caveats**: what trips a reader who uses or changes the folder. What
   the run finds wrong with the code (a script that fails at import, one
   with no caller, a file breaking a repo rule) is a **code finding**: it
   goes in the run report, and in the README only when a reader would hit
   it by running a command the README gives.

The target, a library folder's README, in full:

~~~md
# core

The reusable library: import it, don't run it directly.

```
audio/          # Audio class, VAD, PNAD, loudness normalization, segments
  vad/
    pnad/
      audio_cutter/ # interactive Dash app for manual chunked PNAD segmentation
transcription/  # transcribe() with any model of the registry (models.yaml)
corpus/         # prepared-corpus layout and preparation (resample, augment, prep_manifest.csv)
transcript/     # WER (per clip, list of pairs), text normalization, transcript diff viz
silence_gate/   # silence gates on (nsp, lp): gate files, hypothesis loading, gate fitting
linaw/          # reader of the LINAW annotation database (SQLite or .sql dump)
services/       # external API clients (Deepgram, ElevenLabs, Mistral, LLM)
utils/          # paths, file IO helpers
```
~~~

No Usage and no Caveats: the folder has no command of its own, and each
subfolder's README says what it holds and how to call it.

## Writing

- **Define only what the reader needs.** A repo term that appears only in
  passing is cut with its words, never defined.
- **Name the term.** Write the lexicon term itself, defined where it
  appears (« the marker, the placeholder for an unintelligible passage »),
  never a paraphrase that takes its name later.
- **Mechanism over analogy.** A real command, file or flag with what it
  produces; no metaphor for a mechanism.

Once written, re-read the README for undefined repo terms, metaphors,
overloaded words (« session », « state ») and bare references (« the
pipeline » never introduced), and fix each: the precise term, a defining
clause, or a cut. A finding you cannot fix is reported as « left ».

## The run report

The run's last message (in a review, the agent that ran it carries it in
its own report):

```
write-readme · benchmark/README.md · edit: 2 of 22 passages fail; structure fails
reader: knows speech processing and ASR evaluation (VAD, transcription, WER), has never opened this repo
changed: Tests dropped (inclusion test 1) · How score computes its WER shrunk to a link (inclusion test 2: core/transcript/wer.py says it)
candidates: subset (benchmark/, experiments/, dataset_tools/)
placeholders: none
code findings: none
audit: 2 fixed · 0 left
```

The first line is `write-readme · <path> · ` then the outcome: `draft` for
a missing README, `edit: <n> of <total> passages fail` (the failure
indicator, followed by `; structure fails` when the structure fails; `edit:
0 of <total> passages fail` when all pass), or `full rewrite` when it was
asked for. `changed`, in an edit only, names each old passage edited,
shrunk or dropped with the check it failed; `code findings` each with its
file.

A full rewrite has no `changed` line and adds a `missing facts:` line.
Outside a review, it lists each missing fact with its old passage, its
proposal and its reason:

```
write-readme · README.md · full rewrite
missing facts: 3
  1. The page starts with `view-concept serve --port 8000` (passage 4) · leave: the code contradicts it, the page opens with `view-concept open <slug>`
  2. view-concept was built in a weekend (passage 6) · leave: the reader does not need it
  3. Offline, maths and diagrams show as source (passage 7) · keep: as a link to docs/reference.md, which says it
```

In a review, the line gives only their number (`missing facts: 3`): the
review's agent records each one in the session. A run that read a model
adds `model:` (the facts of the model written that the code does not show,
and those the code contradicted). Add a line when the run wrote the repo lexicon.
