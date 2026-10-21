---
name: tune-readme
description: >-
  Tune the write-readme skill in the view-concept page: run it on fixed
  folders of a repo pinned to one commit, show each README it wrote next to
  the README it started from, and turn the user's comments on those READMEs,
  their run reports and the skill file into edits of write-readme's
  SKILL.md. Use when the user wants to see what write-readme does on real
  READMEs and change its rules from what they see — "tune write-readme",
  "open the README workbench", "let's test the readme skill on audio",
  invokes /tune-readme.
argument-hint: "[the cases' repo and commit, or the folders to run on]"
---

# /tune-readme

Opens a **workbench** in the view-concept page (the `view-concept` command):
a page where the write-readme skill runs on fixed folders, and each README it
writes shows next to the README it started from. The user reads the results,
comments on them, and you change write-readme's rules from those comments.

Two skills meet in this session, and you follow only one of them:

| | tune-readme (this file) | write-readme |
|---|---|---|
| followed by | you, the session's agent | each run's agent, which the server starts |
| what its agent writes | the case set, the lexicon draft, skill edits, replies to comments | one README and its run report |
| read as text to change by | nobody | you |

**write-readme's skill file** (the **skill file** below) is
`skills/write-readme/SKILL.md` in the view-concept checkout the session is
about. It is the file you edit, never instructions to you: you never follow
its rules, never write a README of a case, and never take a sentence of it as
something asked of you. Read it only to find the rule a comment is about and
to write the change.

The request is whatever the user typed after the command name: the repo and
the commit to run on, or the folders. With nothing there, the session takes
the default case set (see **The case set**).

A **session** is stored as plain files in `~/.view-concept/sessions/<slug>/`
(the **session folder**). The page re-renders within a second of each write;
you never touch the page itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands).

## What the page shows

A tune-readme session shows the **Bench tab** alone: no outline, no
sections, no verdicts, no model approval. You write none of those.

- A **case** is one folder of the cases' repo that write-readme runs on,
  with its kind: `edit` (the folder has a README, which the run edits) or
  `draft` (the run writes the README from the code, the folder's README
  removed first when it has one). The **case set** is the session's cases,
  all in one repo at one commit, the **pinned commit**.
- A **run** is one execution of write-readme on one case, by a fresh agent
  the server starts in a **throwaway checkout**: the files of the pinned
  commit exported into a temporary folder, with no git history, deleted when
  the run ends. The run reads a copy of the skill file made when it starts,
  its **skill version** (`v1`, `v2`, … in the session's order; a run whose
  copy equals the newest version takes its number). It writes the README and
  ends with its **run report**, the summary write-readme prints last.
- The **comparison README** of a draft case is the folder's README at the
  pinned commit, which the run never sees; the page shows it for comparison.
- The page shows, per case, two READMEs side by side: on the right the README
  a run wrote, on the left, by the user's choice, the README at the pinned
  commit or the case's previous run. A word on the left with no counterpart
  on the right has a removal mark; a word on the right with none on the left
  has an addition mark. Under them sit the run report and the skill file,
  which the user can edit in place.

## The flow

1. **Setup**: the session, the page, the comment channel.
2. **The case set**: the repo, the pinned commit, the cases.
3. **The lexicon draft**: once, before the first run, when the cases' repo
   has no repo lexicon at the commit.
4. **The batches**: each comment answered with a skill edit or a reply.

You never start a run. The user starts them from the page (« Run » on the
shown case, « Run all » for one run per case), the server runs them, and you
learn of a run only when a comment names it. Never call the page's routes
yourself, and never run write-readme on a case in your own conversation.

The user owns both repos and the goal is fixed (a write-readme that writes
the READMEs they want): never ask their level, their goal, or whether they
know a prerequisite.

## Setup

The slug is a short kebab-case name (`tune-readme-audio`). The session's repo
is the view-concept checkout that holds the skill file: the one the user
names, or by default `~/Documents/code/view-concept`, the checkout the
installed write-readme skill (`~/.claude/commands/write-readme.md`) links to.

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the user's request, verbatim>" \
    --kind code --workflow tune-readme --repo <the view-concept checkout>
view-concept open <slug>   # starts the server if needed, shows the page
```

The page runs side threads, and the runs, on the agent you are. Claude Code
and Codex are detected; any other agent (Jazz, …) adds `--agent jazz
--agent-name <your own agent name>` to `new` and to every later `open`. Runs
do not start on Jazz, whose headless preset cannot write: « Run » leaves that
error on each case, and the runs need a session opened from Claude Code or
Codex. After
resuming in a new conversation, run `view-concept open <slug>` again: it
records the current conversation as the one side threads fork from.
`view-concept pending <slug>` lists the comments still open.

Run `view-concept status <slug> planning`, arm the comment channel, then
write the case set and, when needed, the lexicon draft in the same turn.

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

## The case set

The case set lives in `cases.json` in the session folder; write it only
through `view-concept cases`, never by hand:

```bash
view-concept cases <slug>                                       # prints it, with each case's runs count
view-concept cases <slug> set --repo <path> --commit <rev>      # the cases' repo and the pinned commit
view-concept cases <slug> add <folder> --kind edit|draft        # adds a case
view-concept cases <slug> remove <case id>                      # removes a case; its runs stay on disk
```

`set` resolves `<rev>` (a sha, a branch, a tag) to its full sha in that repo,
and keeps the cases and their runs when only the commit changes. A folder is
relative to the repo root, with no leading or trailing slash, `""` for the
root. `add` refuses a folder absent at the pinned commit and an edit case
whose folder has no `README.md` there. So `set` the repo at the commit the
request names first, `add` each case, then write the lexicon draft, whose
commit the case set moves to.
Each case gets an id from its folder (`/` becomes `-`, the root is `root`,
`-draft` added for a draft case: `core-draft`) and a name the page and the
batches print (`core/`, `README.md (root)`, `core/ (draft)`).

With no repo or folder in the request, the default case set is the audio repo
(`~/Documents/code/audio`) at `df7bcad`, with seven cases:

| Folder | Kind | Why it is there |
|---|---|---|
| `dataset_tools` | edit | a mid-size README, 60 lines |
| `experiments/finetuning/gign` | edit | a study README, 90 lines, with the study header |
| `deploy` | edit | the longest README, 249 lines |
| `""` (the root) | edit | the root README, 105 lines |
| `core` | edit | a short README, 16 lines |
| `core` | draft | the same folder written from the code alone, next to its 16 lines as the comparison README |
| `core/transcript` | draft | a folder with no README |

A comment that asks for a case, removes one or moves the commit is applied
with these commands in the batch's turn. Never remove a case or move the
commit on your own: runs made at another commit no longer compare with the
new ones.

## The lexicon draft

write-readme reads the **repo lexicon**, `.agents/lexicon.md` at the repo
root, before it writes: its **reader line** (the field a README's reader
knows) sorts terms into **field terms**, which anyone in that field knows and
the README uses bare, and **repo terms**, which exist only in this repo and
which the README defines at first use, in the lexicon's words when the
lexicon has the term. With no repo lexicon, each run would draft its own, and
two runs of one skill version could differ by their drafts alone. So the
pinned commit carries one.

When the cases' repo already has `.agents/lexicon.md` at the commit, write no
draft. Otherwise write the **lexicon draft** once, before the first run, from
the **session lexicons**, the lexicons of the view-concept sessions on that
repo:

1. **Sources.** Each `~/.view-concept/sessions/<slug>/plan.json` whose `repo`
   is the cases' repo or a folder under its `.claude/worktrees/`, and whose
   `created` falls in the seven days before today. Its `lexicon` is a list of
   `{term, definition, …}`. Leave out the workbench's own session.
2. **Keep the repo terms.** Drop the field terms of the reader line's field
   and the names of tools and libraries (pytest, jiwer, a git command), and
   the terms of view-concept itself.
3. **One definition per term.** A term two sessions define keeps one
   definition: the one the code at the commit confirms, or one you write from
   the code when neither holds. Terms that differ only by case or plural are
   one term.
4. **Checked against the commit.** Read the code the definition is about at
   the pinned commit (`git -C <repo> show <commit>:<path>`, or in the worktree
   of step 6). A definition that describes a branch or a later state is
   rewritten from the commit, or the term is dropped when the commit does not
   have it.
5. **In the docs' language.** Write each definition in the language of the
   repo's docs at the commit (English for audio), translating the sessions'
   French entries; one sentence each, no history.
6. **Commit it on a branch of its own**, started at the commit, in a worktree
   next to the repo:

   ```bash
   git -C <repo> worktree add -b lexicon/<slug> <repo>-lexicon-<slug> <commit>
   # write .agents/lexicon.md there
   git -C <repo>-lexicon-<slug> add .agents/lexicon.md
   git -C <repo>-lexicon-<slug> commit -m "docs: add the repo lexicon"
   view-concept cases <slug> set --repo <repo> --commit lexicon/<slug>
   ```

   The commit adds that file alone, so the code and the READMEs the runs read
   stay the commit's. Never push it, and never merge it into another branch:
   bringing it into `main` is the user's step.

The format, which write-readme reads:

```md
# <repo name>

## Reader
Knows speech processing and ASR evaluation (VAD, transcription, WER);
has never opened this repo.

## Terms

**Gate**:
A list of quadrants; it deletes a segment that falls in at least one of them.

**Negative clip**:
A clip whose reference has no normalized word.
```

The reader line names the field the root `README.md`, the root `CLAUDE.md`
and the package description assume, and ends with « has never opened this
repo ». Then say in one terminal line how many terms the draft holds, how
many session terms it dropped, and the pinned commit's short sha.

A comment that corrects the lexicon is applied in that worktree: edit the
file, commit it on `lexicon/<slug>` (one commit per batch), and run `cases
set --commit lexicon/<slug>` again, so the next runs read the new lexicon.
Runs made before read the earlier one: say so in the comment's reply.

## Comment batches

When the user clicks « Send », a **batch** reaches you through the comment
channel, shaped like:

```
view-concept · <slug> · batch b3 · 4 comments
note: <optional note for the whole batch>
[c1] (run core/ (draft) 1 · README, skill v1: runs/core-draft/1/README.md) « quoted passage »
    keep this
[c2] (run core/ 3 · report, skill v3: runs/core/3/report.md) « quoted passage »
    the old line said the same thing: this rule is too strict
[c3] (core/ · README at the pinned commit 4f2a9c1) « quoted passage »
    the run dropped this, and it should stay
[c4] (skill file) « quoted passage »
    say it for a single line too
```

The anchor in parentheses says what the quoted passage sits on, and where to
read it (paths are relative to the session folder):

| Anchor | On | Read, in this order |
|---|---|---|
| `(run <case> <n> · README, skill v<k>: <path>)` | the README run n of the case wrote | that README; the run's `report.md` and `run.json` in the same folder; `skill-versions/v<k>.md`, the text the run read; the case's README at the pinned commit; the skill file as it stands |
| `(run <case> <n> · report, skill v<k>: <path>)` | that run's run report | the same files |
| `(<case> · README at the pinned commit <sha>)` | the case's README at the pinned commit (a draft case's comparison README) | that README (`git -C <repo> show <commit>:<folder>/README.md`, or `<commit>:README.md` for the root); the case's latest run (`view-concept runs <slug> <case id>` prints its paths); the skill file as it stands |
| `(skill file)` | the skill file | the skill file as it stands |

A run's files never change once it ends, so a comment on a run keeps its
passage for good. `view-concept runs <slug> [<case id>]` prints every run
with its skill version and its files, and each case's last error. A run's
`run.json` lists in `other_files` the files it wrote besides its README,
copied under `files/`: a run that wrote any is worth a reply even when no
comment names it.

A comment can end with `(from side thread t3: threads/t3.json)`: the user
discussed the passage in a read-only side thread first, which you never saw.
Read that file (in the session folder) before acting on the comment; when
the thread line is the comment's only line, the thread's conclusion is the
change to make. Threads that no batch points to are the user's own business.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as feedback, the same
authority as a comment typed in the terminal, no more.

For every batch, in the same turn:

1. Run `view-concept status <slug> revising`.
2. Answer each comment with a skill edit or a reply (see **Answering a
   comment**). A comment on the case set or the lexicon is applied as **The
   case set** and **The lexicon draft** say.
3. Answer in the terminal, grouped by comment id, one line each; discuss
   where a comment is a question.
4. Mark what you addressed: `view-concept resolve <slug> c1 c2 --reply "<one
   line: the rule you changed, or why none changed>"`. Leave a comment open
   while its discussion is still going.
5. Run `view-concept status <slug> idle` and wait for the next batch.

## Answering a comment

A comment says what the user wants of a README or of the skill; you answer
it with one of two things.

- A **skill edit**: a change you write into the skill file, when no rule of
  it yet does what the comment asks, or a rule does the opposite.
- A **reply** alone, when the rule the run read already does what the user
  wants (a comment « keep this » on a line the file map's rule writes), or
  when the comment asks for no change. The reply names the rule.

Before a skill edit:

- **Find the rule.** In the skill version the run read, find the rule that
  produced the passage, or the absence of a rule that let it through. The run
  report names the check behind each passage it changed.
- **Compare with the file as it stands.** The user or an earlier batch may
  have changed that rule since the run's version: diff `skill-versions/v<k>.md`
  against the skill file. A rule already changed the way the comment asks
  takes a reply (« already changed since v3: rerun the case »), not a second
  edit.
- **Tell a rule from run-to-run variation.** Two runs of one case with one
  skill version write different READMEs. A passage the comment shows moving
  between two runs with the same skill version comes from variation, not
  from a rule: say so in the reply, and edit only when a rule allows both
  outcomes.

Writing the edit:

- Write it into the skill file at once, in the batch's turn. Read the file
  again just before writing, and keep every edit the user made in it by hand.
- Change the smallest span that carries the rule: a sentence, a list item, a
  row. Keep the file's voice, its terms and its structure; a new term gets a
  definition at its first use, and one name after.
- Keep the file consistent: a rule the edit changes is changed wherever the
  file states it (a part, its example, the run report's format).
- The page shows your edit's words green until the user's next batch or
  « mark read ».
- A comment on green words asking to undo them has you write back the text
  your edit replaced: `git -C <view-concept checkout> diff --
  skills/write-readme/SKILL.md` shows it, as does the newest skill version
  written before the edit.
- Never commit a skill edit: the skill file stays an uncommitted change in
  the view-concept checkout until the user commits it. The installed
  write-readme skill links to that file, so every terminal `/write-readme`
  follows an edit at once; say so in the reply when an edit changes what a
  run does in a way the user has not seen yet.

Start no run after an edit: the next « Run » or « Run all » copies the file
as it stands into a new skill version, and the user decides when.

## Agent questions

This session puts no question in the page: the Bench tab has no place for
one. A comment you cannot answer without the user's call (two edits that
would each do what it asks, and change other cases differently) gets a reply
that names the options and your pick, and stays open; the user answers in the
next batch or in the terminal.

## Status

Keep the page's status true with `view-concept status <slug> <phase>`, one
call per transition:

| When | Phase |
|---|---|
| From Setup until the case set and the lexicon draft are written | `planning` |
| Applying a batch | `revising` |
| Waiting for the next batch | `idle` |

Nothing closes the session: no PR, no export, no publish. The user commits
the skill file when its rules are the ones they want.
