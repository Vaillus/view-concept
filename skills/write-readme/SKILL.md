---
name: write-readme
description: >-
  Write a folder's README.md from its code, or rewrite an existing one from
  scratch, against fixed content rules: a reader line and repo terms read
  from the repo's lexicon files, an inclusion test every sentence must pass,
  six parts in a fixed order, and a report printed at the end of the run.
  Use when the user wants a README written for a folder, or an existing
  README cleaned up, shortened or rewritten, notably one written by an LLM —
  "write the README of X", "rewrite this README", "clean up X/README.md",
  "this README is bloated", invokes /write-readme.
argument-hint: "[the folder, or its README.md] [reader: <reader line>]"
---

# /write-readme

Writes the `README.md` of one folder. The folder is whatever the user typed
after the command name: a folder, or the path of its `README.md`. The run
reads the repo's lexicon files, the folder's code and, when there is one,
the old README; it writes the README; it ends by printing its **run report**
(see **The run report**). It writes no other file, apart from the repo
lexicon when the repo has none (see **When the repo lexicon is missing**),
and never commits.

A run has two modes, set by the folder alone:

- **draft mode**: the folder has no `README.md`; the run writes one from the
  code;
- **rewrite mode**: the folder has one; the run reads it as source material
  and writes the README again. No heading, order or wording of the old text
  is kept for being there.

A run never stops before writing, with one exception: a terminal run in a
repo with no repo lexicon asks one question first. Never ask the user's
level, goal, or which passages to keep: the reader line answers the first,
the goal is always that the reader can use or change the folder, and the
inclusion test answers the third.

## The repo lexicon and the reader line

The **repo lexicon** is the file `.agents/lexicon.md` at the repo root. Its
readers are the agents that write the repo's docs; no README links to it.
Its format:

```md
# <repo name>

## Reader
Knows speech processing and ASR evaluation (VAD, transcription, WER);
has never opened this repo.

## Terms

**Registry**:
The list of transcription models and how to build each, one entry per model name.

**Gate**:
A rule fitted per model that deletes a transcribed segment likely to be made up by the model.
```

The `## Reader` part holds the **reader line**: the field a README's reader
knows. That reader has never opened this repo. The `## Terms` part defines
once each term the repo's folders share, one bold term and its definition
per entry.

A **folder lexicon** is a `.agents/lexicon.md` in a folder below the repo
root, in the same format, holding the terms only the folders under it share.
It may state its own reader line, for a part of the repo whose reader knows
another field.

Before anything else, read the repo lexicon, then each folder lexicon from
the repo root down to the README's folder. Where two of them disagree, the
one closest to the README wins:

- for the reader line: the closest lexicon that states one;
- for a term defined in two of them: the closest definition. Such a term is
  a **shadowed term**; list it in the run report, since a redefinition is
  often an accident.

A reader line given in the request (`reader: <line>`) replaces the
lexicons' for this run only; it changes no file.

The reader line sorts each term the README uses into two kinds:

- a **field term** is one anyone in the reader's field knows (WER in a speech
  repo): use it bare;
- a **repo term** exists only in this repo: define it in a clause at its
  first use in the README. When a lexicon on the path has an entry for it,
  the clause is that entry's definition, word for word. When none has it,
  write a definition of your own.

Never link to a lexicon file: the README copies the definition, so its
reader never leaves it. Never edit a lexicon that exists. A repo term
several folders use that no lexicon on the path has is a **candidate**: the
README defines it in a clause of its own, and the run report lists it with
the folders that use it. Never propose a folder lexicon for it: the user
chooses which lexicon takes it.

## When the repo lexicon is missing

When the repo has no `.agents/lexicon.md`, write it before the README.
Draft it from three sources: the root `README.md`, the root `CLAUDE.md`, and
the package description (`pyproject.toml`, `package.json` or the repo's
equivalent). The reader line names the field those sources assume; the terms
are the repo terms several folders' docs share, each with a one-line
definition.

- **Run from the terminal by the user**: show the draft and ask once, before
  writing anything:

  ```
  This repo has no repo lexicon (.agents/lexicon.md). Draft:
  reader: knows speech processing and ASR evaluation (VAD, transcription, WER), has never opened this repo
  shared terms: registry, study, gate
  Correct the reader line or the terms, or answer « ok ».
  ```

  Then write the file with the user's corrections, and the README after it.
- **Run by a review's agent** (the request comes from a rewrite request, or
  names a review's session folder): write the file from the draft without
  asking, then the README. The user corrects it in the review's Doc tab.

This is the only question a run asks.

## Sources

Every fact of the README comes from one of three sources:

1. **The folder's code**: always. Read it before writing: its modules,
   commands, entry points, tests and the files it reads and writes.
2. **The old README**, in rewrite mode.
3. **A review's model**, when the request names a review's session folder:
   the sections in its `sections/` folder and the terms of its lexicon (the
   `lexicon` of its `plan.json`). The model holds the rules of use and the
   conventions a branch decided, which leave no trace in the code.

In rewrite mode, first cut the old README by sections: be willing to lose a
third of them, since a README that grew by added passages has no claim on
the new one. Then check each fact left against the code:

| What the code says | In the new README |
|---|---|
| confirms it | kept, if it passes the inclusion test |
| contradicts it | written as the code has it |
| cannot say (an external link, a deploy caveat) | kept, if it passes the inclusion test |

A fact of the model goes through the same check: one the code contradicts is
written as the code has it and named in the run report; one the code does
not show (a rule on what may import what) is written if it passes the
inclusion test.

A term the model has keeps in the README the name the review's lexicon gives
it. When no lexicon on the path defines it, its clause is the review
lexicon's definition, so the README and the review say one thing.

A rewrite keeps the old README's language. A draft is written in the
language of the repo's other docs.

## The inclusion test

A sentence stays only if both conditions hold:

1. the reader needs it to use or change this folder;
2. no other code or doc already says it.

A sentence that fails only the second shrinks to a few words and a link to
where it is said (« score uses the repo's WER », linking the WER module). A
lexicon definition is the exception: the README copies it, since no README
links to a lexicon.

The **never-include list** names what fails the test every time; drop it
without weighing each sentence:

- history: how the folder came to be, what it replaced, which PR changed it;
- open discussions: options under consideration, ideas, to-dos;
- rules restated from elsewhere: a rule another doc or the code states.

The one exception is a **migration note**: a dated passage saying how to
read the outputs made before a change (old names, old defaults). It stays,
with the date after which it can go. A run past that date drops it and
lists it among the dropped passages of the run report.

## The six parts

Write every README in these six parts, in this order. Only the first
sentence is required: leave out any other part the folder has nothing for.
Name the headings freely.

1. **The first sentence**: the folder in one sentence, in field terms, or
   with the repo terms it cannot avoid defined in it. When it cannot be
   written, the folder has no single purpose: write the README anyway, and
   say so in the run report.
2. **The file map**: one line per file or subfolder that matters, under the
   name the reader would search for, with what it holds. Never a full tree.
   Once a file is named here, the parts after it use the name without
   explaining it.
3. **The status line**: only when the folder is not in normal use:
   experimental, deprecated, or replaced by another folder (named).
4. **Usage**: the commands, each with what it produces.
5. **Invariants**: an **invariant** is a rule the folder's code keeps that
   reading the code does not show, which a change to the folder must not
   break.
6. **Caveats**: what else trips a reader up, a migration note among them.

A reader looks a README up by task and skips the rest, so no part is there
to set up a later one, and a forward pointer (« see Caveats ») is fine where
a passage only needs to name what a later part develops. Every repo term is
still defined at its first use, wherever that falls.

## Writing

- **The lexicon contract.** The run's lexicon starts from the entries of the
  lexicons on its path. Every repo term in the README is in it and defined
  in a clause at its first use, in its entry's words when it has one. A term
  you are about to write that is in no lexicon and has no definition: add a
  definition, or cut the sentence.
- **Mechanism over analogy.** A command with what it produces, a real file
  name, a real flag, where a paragraph would describe them. No metaphor
  stands for a mechanism.

## The vocabulary audit

Once the README is written, re-read it for:

- **undefined terms**: a repo term with no definition at its first use;
- **metaphors** standing for a precise mechanism or structure;
- **overloaded words** whose meaning depends on context the reader lacks
  (« session », « state », « context »);
- **bare references**: a definite article on a noun the README has not
  introduced (« the pipeline », « the config »).

Fix each finding yourself: replace it with the precise term, define it in a
clause, or cut the sentence. A finding you cannot fix stays in the README
and goes in the run report as « left », with its sentence.

## The run report

The run ends by printing this report, its last message (in a review, the
agent that ran it carries it in its own report or reply):

```
write-readme · benchmark/README.md · rewrite mode
reader: knows speech processing and ASR evaluation (VAD, transcription, WER), has never opened this repo
from lexicon: registry · study · gate (.agents/lexicon.md)
own words: harness, hypothesis cache, offline mode (this folder only)
candidates: subset (13 docs use it, in benchmark/, experiments/ and dataset_tools/; no lexicon on the path has it)
shadowed: none
dropped: Tests (not needed to use or change the folder)
audit: 2 fixed: « the pipeline » named the USB deploy · « airgap » defined · 0 left
```

- **reader**: the reader line used, with « (from the request) » when the
  request gave it;
- **from lexicon**: the repo terms defined in a lexicon's words, grouped by
  the lexicon file they come from;
- **own words**: the repo terms defined in the run's own words;
- **candidates**: each with the folders that use it;
- **shadowed**: each shadowed term, with the two lexicons that define it;
- **dropped** (rewrite mode): each passage of the old README the new one
  does not hold, with its reason (which condition of the inclusion test it
  fails, the never-include list, or a migration note past its date);
- **audit**: the findings fixed, and those left with their sentence.

A run started from a review adds two lines:

```
from review: public API (review lexicon, this folder only)
model: 1 written the code does not show: a study imports only load_dataset and score · 0 contradicted by the code
```

- **from review**: the terms defined in the review lexicon's words;
- **model**: the facts of the model written that the code does not show, and
  those the code contradicts, written as the code has it.

Add a line when the first sentence could not be written, and when the run
wrote the repo lexicon.
