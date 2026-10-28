---
name: write-readme
description: >-
  Write a folder's README.md from its code, or bring an existing one up to
  standard, editing only what fails and counting the passages that fail, or
  write it again from the code alone when asked and list the facts the old
  one said that the new one lost, always on its own parts only: the first
  sentence, the file map under ## Files, the status line, the usage under
  ## Usage, and a section the repo's conventions impose. Every other
  passage, the folder model the document-feature skill holds, stays word
  for word. Fixed content rules: a reader line and repo terms read from the
  repo's lexicon files, an inclusion test every sentence of its parts must
  pass, the repo's own README conventions, and a report printed at the end
  of the run.
  Use when the user wants a README written for a folder, or an existing
  README cleaned up, shortened or rewritten, notably one written by an LLM —
  "write the README of X", "rewrite this README", "clean up X/README.md",
  "this README is bloated", invokes /write-readme.
argument-hint: "[the folder, or its README.md] [rewrite | removed] [reader: <reader line>] [a review's session folder]"
---

# /write-readme

Writes the `README.md` of one folder: the folder, or its `README.md`, is
whatever the user typed after the command name, followed by `rewrite` when
the user asks for a full rewrite (`/write-readme <folder> rewrite`), or by
`removed` when a review's doc pass names the README of a folder its branch
removes. The run
reads the repo's lexicon files, the folder's code and the old README if
there is one, writes its parts of the README (see **Its parts**), and ends
by printing its **run report**. It writes no other file (except the repo
lexicon when the repo has none) and never commits.

A run has one of four outcomes:

- **draft**: the folder has no `README.md`; write its parts from the code;
- **edit** (always, when it has one and no full rewrite was asked for): keep
  the structure, headings and wording of its parts, change only the
  passages of its parts that fail a check, count the **failure indicator**
  (see **Checking an existing README**), and leave every other passage word
  for word;
- **full rewrite**: only on a **rewrite request**, the `rewrite` argument or
  a review's request to write a README again from scratch; write its parts
  again from the code alone, without reading the old ones, as for a draft,
  copy every other passage after them word for word, then list the
  **missing facts** of its parts (see **The missing facts**);
- **retitle only**: only with the `removed` argument, on the README of a
  folder the branch removes; retitle it (see **Its parts**) and do nothing
  else: there is no code left to describe, so check no passage, write
  nothing from the code, count no failure indicator and list no missing
  fact. The document-feature skill then reads the boundary by these
  headings for its move plan, and deletes the file once every passage of
  its folder model has moved.

The run never chooses a full rewrite on its own, however much of its parts
fails: the failure indicator tells the user, who decides.

A run is **in a review** when its request names a review's session folder
(`~/.view-concept/sessions/<slug>/`): a feature's doc pass or a docs review
started it as an agent of its own, on one README, and the review's page
shows what the run leaves to the user. Any other run, a `rewrite` argument
typed in a terminal included, is outside a review. In a feature's doc pass,
this skill runs on each README before the document-feature skill, which
then reads the boundary of its parts by their headings (see **Its parts**)
and writes the folder model after them.

In a review, the request may also carry the user's comments on the
README's parts, each with its id, its quote and its text: apply each in its
parts, under this skill's rules, and leave it open (the review resolves
it). A comment on a passage of the folder model is not this skill's: name
it in the run report. The request may carry a missing fact the user keeps
(see **The missing facts**): add it to its parts.

Never ask the user anything, except the one question of **The repo
lexicon** below: the reader line says who reads, the goal is always that the
reader can use or change the folder, and the inclusion test says what stays.

## Its parts

A README is shared, passage by passage (a paragraph, a list, a table, a
code block), between this skill and the **folder model**. This skill holds
only its **parts**:

1. **the first sentence**: the folder in one sentence;
2. **the file map**: one line per file or subfolder that matters;
3. **the status line**: whether the folder is experimental, deprecated or
   replaced;
4. **the usage**: the folder's own commands, each with what it produces;
5. a section the repo's conventions impose (a study header).

Every other passage of a README is the **folder model**: the rules to know
to use the folder without a mistake, as the code applies them, and
whatever else an existing README already held (a caveat, a data format,
links, history, an open discussion). The document-feature skill holds it,
from the model of the feature in progress. This skill never writes, checks,
moves or cuts a passage of the folder model, in any outcome: an edit leaves
each one word for word in its place, unchecked; a full rewrite copies them
word for word after its parts. A placeholder (« TODO: Notion link ») or a
dated migration note belongs to the part it sits in.

**The headings.** This skill always titles the file map `## Files` and the
usage `## Usage`, and recognises those two parts by these headings. The
first sentence, the status line and a study header stay untitled,
recognised by their place at the top of the README, before the first `##`
heading. A passage under any other `##` heading is the folder model. A
usage section of its own (`## Rebuilding a corpus`) keeps its title as a
subheading under `## Usage` (`### Rebuilding a corpus`). When the repo's
conventions impose other headings for the map or the usage, they replace
`## Files` and `## Usage`, and the parts are recognised by them.

**The retitling.** An existing README whose map and usage are not under
these headings (one this skill never ran on since it titles them) is
retitled once, by the first edit that finds it so, in a review the first
doc pass whose doc set holds it, or by a retitle-only run (the README of a
folder the branch removes, with `removed`). That run judges the role of each passage:
the map goes under `## Files`, the usage sections are gathered under
`## Usage`, each with its own title as a subheading, and a mixed section is
split, its map table going under `## Files` while the rest (a data format,
a caveat) stays under the section's own heading, in the folder model.
`## Files` and `## Usage` come right after the untitled top, then the
folder model's sections, in their old order. This is the only time an edit
moves or retitles a passage; the passages move word for word, and the
retitling is named in the run report's `retitled:` line. Every later edit
recognises the parts by their headings, without judging.

Before the retitling of `experiments/finetuning/gign/README.md`:

```md
# GIGN fine-tuning
**Status.** … **Data.** … **Result.** …
Code of the GIGN fine-tuning study, …

## The corpora
(the split format · the table of scripts · a caveat)
## Rebuilding a corpus
## Scoring the marker
## See also
```

After it:

```md
# GIGN fine-tuning
**Status.** … **Data.** … **Result.** …
Code of the GIGN fine-tuning study, …

## Files
(the table of scripts)
## Usage
### Rebuilding a corpus
### Scoring the marker
## The corpora
(the split format · the caveat)
## See also
```

A full rewrite of a README never retitled recognises its parts by the same
judgment, then writes them under the fixed headings.

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

Every fact of its parts comes from the folder's code (always read first:
modules, commands, entry points, tests, the files it reads and writes), the
old README's parts for an edit, the missing facts the user keeps after a
full rewrite, and the model of each session folder the request names that
holds one (its `sections/` and the `lexicon` of its `plan.json`), for what
its parts need that the code does not show (what a command is for). The
rules of the model are the folder model's, not this skill's. A feature
names its own folder; a docs review names its own, which holds no model,
and its reference model's folder when it has one. A fact the code
contradicts is written as the code has it. A term the review's lexicon has
keeps its name there, and its definition when no lexicon on the path has
the term.

Before writing, read the rules the repo sets for READMEs, in the root
`CLAUDE.md` (or `AGENTS.md`) and the READMEs from the root down to the
folder (a study header, a required section). They win over this skill.

An edit keeps the old README's language; a draft and a full rewrite take
the language of the repo's other docs.

## Checking an existing README

An edit goes through the passages of its parts one by one and marks each
passage that fails:

1. the inclusion test;
2. the code: a fact the code contradicts. A rule the README states that
   some code breaks (« no CLI in `core/` » while a module has one) is not
   contradicted: the passage passes, and the code is a code finding;
3. the vocabulary: a finding of the audit (see **Writing**);
4. the repo's README conventions.

Fix each failing passage where it stands and leave the others word for
word; apart from the retitling (see **Its parts**), never move, merge or
retitle sections. A passage that fails only by leaving something out (a
file missing from the map) is fixed by adding the line. The folder model's
passages are not checked: a wrong path in the usage is this skill's to fix,
a wrong rule in the folder model is document-feature's. A README can come
out unchanged.

The **failure indicator** is the number of passages of its parts that fail
a check, counted before the edit, out of the passages of its parts: `3 of 6
passages fail`. A passage that fails only by leaving something out does not
count, and the folder model's passages count in neither number. When the
structure of its parts itself fails (a usage with a subsection per module
and a list of return fields), the indicator says so too (`structure
fails`); the edit does not fix the structure, and the run stays an edit.
The indicator is in the first line of the run report.

## The missing facts

A full rewrite never reads the old README's parts while it writes; it reads
the old README only to set its folder model aside, which it copies word for
word after the new parts. Once the new README is written, compare the old
parts with the new: read the old parts fact by fact (one thing they state:
a command, a path, a reason) and keep each fact the new README says neither
in words nor by a link to a doc that says it. These are the **missing
facts**. A fact the new README says in other words, once instead of three
times, or as a link, is not missing. The folder model, copied whole, has no
missing fact.

For each missing fact, give:

- the fact itself, in one sentence;
- the number of the old passage that held it, counted from the top of the
  old README;
- your proposal, **keep** or **leave**, with a reason in one line: keep when
  the reader needs it (and in what form it would come back: a sentence, or a
  link to the doc that says it), leave when it fails the inclusion test. A
  fact the code contradicts is listed too, proposed leave, with that reason
  (« the code contradicts it: the page opens with `view-concept open` »).

The proposal drops nothing: the new README stays as written, and the user
decides which facts come back. A fact the user keeps is added to the
README's parts under this skill's rules, so the inclusion test can make it
a link. Outside a review, the user reads the list in the run report and
names the facts to keep in a later message; in a review, the run report
lists them the same way, the review records them in the session, and the
user decides in the page. An edit has
no missing facts: the passages it changes are named in the report's
`changed` line.

## The inclusion test

Every sentence of its parts, in a draft, a rewrite or an edit, stays only
if:

1. the reader needs it to use or change this folder. A sentence that gives
   the reason the folder is built the way the reader sees it (two pairs of
   scripts, a separate archive) passes;
2. no other doc file already says it. Another passage of the same README
   does not count.

A sentence that fails only the second shrinks to a few words and a link.
Drop history and open discussions (ideas, to-dos) from its parts, except a
**placeholder** for a missing link or fact (« TODO: Notion link », kept and
listed in the report) and a dated **migration note** on reading outputs
made before a change, kept until its date. The test never reaches the
folder model: a history or an open discussion there stays word for word.

## Writing its parts

A draft or a full rewrite writes its parts in this order, unless the repo's
conventions set another shape: the untitled top (a study header the
conventions impose, the first sentence, the status line), then `## Files`,
then `## Usage`. A full rewrite then copies the folder model's passages
word for word, headings included, in their old order. A draft has no
folder model: document-feature adds one after its parts, under a `##`
heading of its own, when a feature gives the folder rules.

- **Depth.** A README covers its folder at the level of its direct
  children, and says nothing about what lies inside a subfolder: that
  belongs to the subfolder's README, and what a module does to its
  docstrings. A deeper folder gets a line only when a reader would look for
  it by name (an app of its own).
- **Start minimal.** A draft starts as the first sentence and the file map.
  Add another part only when the folder has something for it the map
  cannot show.

1. **The first sentence**: the folder in one sentence, in field terms.
2. **The file map**, under `## Files`: one line per file or subfolder that
   matters, with what it holds in a few field words, and a link to its
   README when it has one. A map line defines no repo term.
3. **The status line**: only when the folder is experimental, deprecated,
   or replaced (by what).
4. **The usage**, under `## Usage`: the folder's own commands, each with
   what it produces; for a library, one short call example per public
   entry point. No subsection per module, no list of return fields.

No part for caveats: a caveat is a rule to know to avoid a mistake, which
the folder model holds, so this skill never writes one and leaves an
existing one word for word. What the run finds wrong with the code (a
script that fails at import, one with no caller, a file breaking a repo
rule) is a **code finding**: it goes in the run report only.

The target, a library folder's README, in full:

~~~md
# core

The reusable library: import it, don't run it directly.

## Files

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

No `## Usage`: the folder has no command of its own, and each
subfolder's README says what it holds and how to call it.

## Writing

- **Define only what the reader needs.** A repo term that appears only in
  passing is cut with its words, never defined.
- **Name the term.** Write the lexicon term itself, defined where it
  appears (« the marker, the placeholder for an unintelligible passage »),
  never a paraphrase that takes its name later.
- **Mechanism over analogy.** A real command, file or flag with what it
  produces; no metaphor for a mechanism.

Once written, re-read its parts for undefined repo terms, metaphors,
overloaded words (« session », « state ») and bare references (« the
pipeline » never introduced), and fix each: the precise term, a defining
clause, or a cut. A finding you cannot fix is reported as « left ».

## The run report

The run's last message (in a review, the review reads it and records what
it gives: the failure indicator and the missing facts):

```
write-readme · benchmark/README.md · edit: 2 of 9 passages fail; structure fails
reader: knows speech processing and ASR evaluation (VAD, transcription, WER), has never opened this repo
retitled: script table moved under ## Files · Running and Adding a model gathered under ## Usage
changed: Tests dropped (inclusion test 1) · run_benchmark.py path corrected (code)
candidates: subset (benchmark/, experiments/, dataset_tools/)
placeholders: none
code findings: none
audit: 2 fixed · 0 left
```

The first line is `write-readme · <path> · ` then the outcome: `draft` for
a missing README, `edit: <n> of <total> passages fail` (the failure
indicator, over the passages of its parts, followed by `; structure fails`
when the structure of its parts fails; `edit: 0 of <total> passages fail`
when all pass), `full rewrite` when it was asked for, or `retitle only`
with `removed`, whose report has its first line and its `retitled:` line
alone (`retitled: none` when the README already had its headings).
`retitled`, in the edit or the retitle-only run that retitles the README,
names each passage moved and each
heading set; `changed`, in an edit only, names each old passage edited,
shrunk or dropped with the check it failed; `code findings` each with its
file.

A full rewrite has no `changed` line and adds a `missing facts:` line,
which lists each missing fact with its old passage, its proposal and its
reason, in a review too:

```
write-readme · README.md · full rewrite
missing facts: 3
  1. The page starts with `view-concept serve --port 8000` (passage 4) · leave: the code contradicts it, the page opens with `view-concept open <slug>`
  2. view-concept was built in a weekend (passage 2) · leave: the reader does not need it
  3. `view-concept open --no-browser` starts the server without opening a browser (passage 5) · keep: as a sentence of the usage
```

A run that read a model
adds `model:` (the facts of the model its parts use that the code does not
show, and those the code contradicted). Add a line when the run wrote the
repo lexicon.
