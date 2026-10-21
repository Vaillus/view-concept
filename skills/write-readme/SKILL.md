---
name: write-readme
description: >-
  Write a folder's README.md from its code, or bring an existing one up to
  standard, editing only what fails, against fixed content rules: a reader
  line and repo terms read from the repo's lexicon files, an inclusion test
  every sentence must pass, the repo's own README conventions, five parts for
  a new README, and a report printed at the end of the run.
  Use when the user wants a README written for a folder, or an existing
  README cleaned up, shortened or rewritten, notably one written by an LLM —
  "write the README of X", "rewrite this README", "clean up X/README.md",
  "this README is bloated", invokes /write-readme.
argument-hint: "[the folder, or its README.md] [reader: <reader line>]"
---

# /write-readme

Writes the `README.md` of one folder: the folder, or its `README.md`, is
whatever the user typed after the command name. The run reads the repo's
lexicon files, the folder's code and the old README if there is one, writes
the README, and ends by printing its **run report**. It writes no other file
(except the repo lexicon when the repo has none) and never commits.

A run has one of three outcomes:

- **draft**: the folder has no `README.md`; write one from the code, in the
  five parts;
- **edit** (the default when it has one): keep its structure, headings and
  wording, and change only the passages that fail a check;
- **full rewrite**: most of the old README fails; write it again in the five
  parts, using it as source material.

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
terms, or answer « ok » »), then write it. Run by a review's agent (the
request comes from a rewrite request or names a review's session folder),
write it without asking.

## Sources

Every fact comes from the folder's code (always read first: modules,
commands, entry points, tests, the files it reads and writes), the old
README, and, when the request names a review's session folder, the review's
model (its `sections/` and the `lexicon` of its `plan.json`), which holds
rules the code does not show. A fact the code contradicts is written as the
code has it. A term the review's lexicon has keeps its name there, and its
definition when no lexicon on the path has the term.

Before writing, read the rules the repo sets for READMEs, in the root
`CLAUDE.md` (or `AGENTS.md`) and the READMEs from the root down to the
folder (a study header, a required section). They win over this skill.

An edit or a full rewrite keeps the old README's language; a draft takes
the language of the repo's other docs.

## Checking an existing README

Go through the old README passage by passage (a paragraph, a list, a
table, a code block) and mark each passage that fails:

1. the inclusion test;
2. the code: a fact the code contradicts. A rule the README states that
   some code breaks (« no CLI in `core/` » while a module has one) is not
   contradicted: the passage passes, and the code is a code finding;
3. the vocabulary: a finding of the audit (see **Writing**);
4. the repo's README conventions.

Edit by default: fix each failing passage where it stands and leave the
others word for word; never move, merge or retitle sections. Rewrite in
full only when more than half the passages fail, or when the structure is
itself the failure (a section of open discussion as large as the rest).
A passage that fails only by leaving something out (a file missing from the
map) is fixed by adding the line and does not count. A README can come out
unchanged.

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
write-readme · benchmark/README.md · full rewrite: 14 of 22 passages fail
reader: knows speech processing and ASR evaluation (VAD, transcription, WER), has never opened this repo
changed: Tests dropped (inclusion test 1) · How score computes its WER shrunk to a link (inclusion test 2: core/transcript/wer.py says it)
candidates: subset (benchmark/, experiments/, dataset_tools/)
placeholders: none
code findings: none
audit: 2 fixed · 0 left
```

The first line is `draft`, `edit: <changed> of <total> passages` (`edit: no
change` when all pass), or `full rewrite` with its reason. `changed` names
each old passage edited, shrunk or dropped with the check it failed;
`code findings` each with its file. A run from a review adds `model:` (the
facts of the review's model written that the code does not show, and those
the code contradicted). Add a line when the run wrote the repo lexicon.
