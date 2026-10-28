---
name: review-docs
description: >-
  Review a repo's docs on a scope in the view-concept page, with no branch to
  model: list the docs the scope concerns, correct what the code contradicts,
  flag what another session's model contradicts, rewrite the docs on each
  comment batch, then open a PR on a docs branch of its own. Use when the
  user wants docs checked, brought up to date or rewritten — "review the
  docs about X", "are the install docs still right", "update the docs of
  this folder", invokes /review-docs.
argument-hint: "[the docs to review: a folder, files, or a subject]"
---

# /review-docs

Reviews a repo's docs in the view-concept page (the `view-concept` command):
the list of docs a scope concerns, each doc shown as it is in a worktree of
its own, corrected where the code contradicts it, then rewritten on the
user's comments until a PR carries it. You do the review yourself, but for
write-readme's parts of each README, which a write-readme agent you start
writes (see **Running write-readme**).

The scope to review is whatever the user typed after the command name: a
folder, a list of files, or a subject (« everything about the install »).
When it names a feature whose model to measure the docs against
(« with the model of doc-tab »), that is the reference model (see **The
reference model**); otherwise you look for one at the first run.

The terminal is a bad place to read docs: every new message pushes them
further up the scrollback. So the docs live in the page, and the terminal
only drives the conversation. The user reads in the page, and sends comments
on selected passages back to this session in batches.

A **session** is the review, stored as plain files in
`~/.view-concept/sessions/<slug>/` (the **session folder**). You write the
doc set there and the docs in the worktree; the page re-renders within a
second of each write; you never touch the page itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands).

## The flow

1. **Setup**: a branch and its worktree, the session and the page, the
   comment channel.
2. **The doc set**: the list of docs the scope concerns, each with its
   reason.
3. **The first run**: the search for a reference model, the docs written
   in the write order (each README's parts by a write-readme agent, the
   stale passages the code contradicts corrected in its folder model and
   in the other docs), the minor docs classed, the passages the reference
   model contradicts flagged.
4. **The batches**: each batch's comments rewrite the docs at once.
5. **« Create PR »**: one commit and the PR; each later batch adds a commit
   and updates the PR.

The user owns the repository and the goal is fixed (docs that say what the
code does): never ask their level, their goal, or whether they know a
prerequisite.

## Setup

The slug is a short kebab-case name of the scope (`install-docs`). The
review works on a branch of its own, `docs/<slug>`, made from `main`, in a
worktree next to the repo, the folder `<repo>-<slug>` (for the repo
`~/code/shop`, `~/code/shop-install-docs`):

```bash
git -C <repo root> worktree add -b docs/<slug> <repo root>-<slug> main
view-concept new "<title>" --slug <slug> --initial-request "<the user's request, verbatim>" \
    --kind code --repo <the worktree> --base main --workflow review-docs
view-concept reference <slug> <other slug> --reason "<one line>"   # when the request names one
view-concept open <slug>   # starts the server if needed, shows the page
```

`--repo` is the worktree, not the main checkout: the page reads each doc
there, and compares it with `main` for the base mark. Every file you change
is in the worktree.

The workflow makes the page show the Doc tab alone. The page runs side
threads on the agent you are. Claude Code and Codex are detected; any other
agent (Jazz, …) adds `--agent jazz --agent-name <your own agent name>` to
`new` and to every later `open`. After resuming in a new conversation, run
`view-concept open <slug>` again: it records the current conversation as the
one side threads fork from. `view-concept pending <slug>` lists the comments
still open.

Then arm the comment channel and run `view-concept status <slug> planning`.

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

## The doc set

The **doc set** is the list of the repo's doc files the review covers, each
with a one-line reason it is listed. It lives in `doc-set.json` in the
session folder; write it only through `view-concept doc-set`, never by hand:

```bash
view-concept doc-set <slug>                                 # prints it
view-concept doc-set <slug> add <path> "<reason>" [--user]  # adds a doc, or changes its reason
view-concept doc-set <slug> remove <path> [--user]          # removes a doc
view-concept doc-set <slug> order <path> <path> ...         # puts the doc set in the write order
view-concept doc-set <slug> minor <path> "<reason>" --added N --removed N   # classes a doc minor
view-concept doc-set <slug> major <path>                    # takes the minor class off
view-concept doc-set <slug> failing <path> <fail> <total> [--structure]     # a README's failure indicator
view-concept doc-set <slug> failing <path> --clear          # removes it
```

`order` takes every doc of the doc set once, and refuses a path missing or
not listed. `add` on a doc already listed keeps its minor class and its
failure indicator. The printed doc set shows each minor doc's reason with
its diff size (`+a −r`) and each README's indicator (`n/total failing`).

A path is relative to the repo root and may name a doc the review will
create. `--user` marks a change the user asked for in a comment: a doc the
user removed is recorded as removed, and `add` refuses it from then on unless
the user asks for it back (`--user` again). Never add back on your own a doc
the user removed.

Write it from the scope, after reading the repo's docs (README files, a
`docs/` folder, `CLAUDE.md` files, skill files, any Markdown the repo keeps
for readers):

- a folder or a list of files: the docs among them, then the `README.md` and
  the `CLAUDE.md` of each folder of the scope and of its parents, up to the
  repo root;
- a subject: every doc with a passage about it, wherever it sits;
- always, present or missing, the **repo lexicon**, `.agents/lexicon.md` at
  the repo root (the reader line, the field the docs' reader knows, and one
  definition per term the repo's folders share), and each **folder lexicon**
  (a `.agents/lexicon.md` below the root, for the terms only the folders
  under it share) above the folder of a doc of the doc set. A missing repo
  lexicon is listed so its entry in the Doc tab carries « write repo
  lexicon »; you write it only on that request, a rewrite request, or at
  the first run when the doc set holds a README (see **The first run**).

The reason is one line the user reads in the list: what in the doc the scope
concerns (« the Install part: the Claude Code plugin, Jazz, Codex, the other
agents »), not why the rule let it in. Docstrings and code comments are not
docs and stay out. A doc outside the scope enters the doc set when a comment
asks for it.

A docs review has no branch to model, so no rule adds the `README.md` a
folder lacks: a folder gets a new README only when a comment asks for it.

### The write order

The first run writes the docs in the **write order**, each folder's docs
after those of its subfolders, so that a parent README finds its children
already written and can link to them instead of repeating them:

1. the lexicons: the repo lexicon when it is missing (see **The repo
   lexicon**);
2. the docs of each **central subtree**, each folder after its subfolders;
3. the other docs, by the same rule;
4. the root `README.md`;
5. the `CLAUDE.md` and `AGENTS.md` files, last, so they can link to the
   docs they come after instead of repeating them.

A **central subtree** is a folder, and what it holds, that holds a file the
reference model's `code-map.md` (in its session folder) ties to a **core
concept**: a term whose entry in the `lexicon` of that session's `plan.json`
has `kind: core`. Between two central subtrees, the first is the one whose
core concept comes first in the reference model's sections. Without a
reference model, or while the question choosing it is open, no subtree is
central: the order goes from the leaves to the root only, `CLAUDE.md` last.

Record the order with `view-concept doc-set <slug> order <path> ...` before
writing; the Doc tab lists the docs in it. A doc that enters the doc set
later is put at its place in the order (`order` again).

### Minor docs

A **minor doc** is a doc of the doc set the first run changed only for a
detail with no effect on its meaning (a path a move renamed, a name added
to a list). Once the first run has written the docs, class each one with
`view-concept doc-set <slug> minor <path> "<reason>" --added N --removed
N`: the reason in one line (« renames `core/` to `lib/` in the file map »),
and the doc's diff size against the base branch, in lines added and
removed (`git -C <worktree> diff --numstat main -- <path>`). Never class
minor a doc the review creates or a doc the first run did not change. Only
the first run classes; after it, a comment on the list moves a doc either
way (`minor` or `major`).

## The Doc tab

The page shows the review in the **Doc tab**, the only tab of a docs review:
your open questions at the top, then the doc set, each doc with its reason
and its count of stale passages, then one doc at a time, read from the
worktree at each render, so your rewrites and the user's own edits show
alike. A doc carries two marks: the **base mark**, a blue bar in the right
margin of each block that differs from the same doc on `main`, with a blue
background on the words it adds (the whole text for a doc the review
creates), so it shows at any time what the PR will hold; and the green
highlight of what changed since the user's last batch. The user may also
edit a doc by hand in the page, which writes the file in the worktree: read
a doc again before rewriting it, and keep the user's edits.

The doc set shows first the **review list**, the docs the user is asked to
read (every doc that is not minor, and a minor doc on which a stale passage
is shown or with a missing fact still `pending`), then a fold « n minor
docs », each with its reason and `+a −r`; the title bar lists the docs in
the write order, the minor docs after the review list, set back. Each
README that carries a failure indicator shows « n/total failing » next to
it, and its rewrite button (« rewrite <path> with write-readme ») is put
forward when more than half its passages fail or its structure fails. Under
a README rewritten in full, the tab lists its « n missing facts », each
with write-readme's proposal, its reason and its state (pending, kept,
left); the user comments on a fact as on a passage of the doc.

When the session has a reference model, the terms of its lexicon are
underlined in the docs with their definition on hover, and the top bar links
to its session, with the reason you kept it next to the link. « Create PR »
sits at the end of the tab.

## The first run

Once the session is open, in the same turn:

1. Write the doc set (see **The doc set**).
2. Unless the request named one, look for a reference model (see **The
   reference model**).
3. Run `view-concept status <slug> revising`, record the write order (see
   **The write order**), and write the docs in it: on each `README.md` of
   the doc set, start a write-readme agent for its parts and record what
   its report gives (see **Running write-readme**), then, once it has
   ended, correct the stale passages the code contradicts in its folder
   model; in every other doc, look for the stale passages (see **Stale
   passages**) and correct those the code contradicts, in the doc files.
   A `CLAUDE.md` or `AGENTS.md` comes last, under the sentence test (see
   **Writing a doc**).
4. Class the minor docs (see **Minor docs**).
5. Flag the passages the reference model you kept contradicts.
6. Ask what the reading left open (see **Agent questions**): a doc whose
   place in the scope you cannot tell, a correction that needs the user's
   call.
7. Run `view-concept status <slug> awaiting-pr` (the page shows « Create
   PR ») and say in one terminal line how many docs the doc set holds, how
   many of them are minor, how many passages you corrected, the reference
   model you kept (or none) and how many passages you flagged.

The user's first batch therefore starts from the corrections made: the base
mark shows each one, since nothing else has changed on the branch yet. A
correction that went the wrong way (a path renamed where the paragraph
should have gone) is undone by a comment.

## Stale passages

A **stale passage** is a passage of a doc of the doc set that something more
reliable than the doc contradicts. Two checks find them.

**The code check.** A doc cites names: a path, a command, a command's flag,
a function, a class, an environment variable, a section of another doc. Read
each citation and check that the repo still has it (the file, the command in
the CLI's parser, the function in the code, the variable read somewhere, the
heading in the doc). Check nothing outside the repo (`~/.cache/…`) and no
file the code writes at run time (a session file the doc names, a log): the
repo cannot say whether those exist. This is not a script: you read each
citation and decide. What the code contradicts, correct in the doc without
waiting for a batch: a moved path takes its new name, a removed command
leaves the doc with the sentence that describes it, a renamed function its
new name. A correction is the smallest change that makes the passage true.

**The reference model.** What the code cannot say (a doc that is wrong by
what it leaves out, a rule stated otherwise) needs a measure: the
**reference model**, the model of a feature of the same repo whose
sections and lexicon say what the code now does or is about to do. Most
docs reviews have none: the review then measures its docs against the code
alone, and that is the ordinary case, not a gap to fill. **The reference
model** below says how you find one. Re-read its `plan.json` (outline and lexicon) and its `sections/` in
`~/.view-concept/sessions/<other slug>/` at each run, as they are then. A
passage it contradicts is flagged, not corrected: a contradiction with a
model needs the user's judgment, where a dead name needs none.

```bash
view-concept stale <slug> <doc path> "<quote>" "<note>" --section <section id>
```

- the quote is the passage's exact text, as in the file (the page finds it
  there and draws a wavy underline on it): the shortest span that shows the
  contradiction, with no Markdown markup it would not match;
- the note is one line: what the reference model says instead;
- `--section` names the reference model's section the passage contradicts.

The command prints the flag's id (`s3`); `view-concept stale <slug>` lists
the flags still shown; `view-concept stale <slug> --drop <id>` removes one.
A flag whose quote is no longer in the doc is no longer shown, so a rewrite
of the passage clears it. Flag no passage that is true: each one costs the
user a comment.

Run both checks on every doc of the doc set at the first run, then on each
doc you rewrite or add to the doc set, in the same run. A reference model
set after the first run (by an answer or a comment) makes you check
**every** doc of the doc set against it at the run that sets it, the docs
read at the first run included, not only those rewritten since.

## The reference model

Only the repo's features are candidates: an explanation or a triage
has no model. You search for one at the first run only; after it, only a
comment sets, changes or removes one.

```bash
view-concept reference <slug> --candidates                       # the repo's features
view-concept reference <slug> <other slug> --reason "<one line>"  # keeps one
view-concept reference <slug> --clear                            # removes it
view-concept reference <slug>                                    # prints it
```

`--candidates` lists each feature of the repo (any worktree) with its
title, the titles of its model's sections and its lexicon's terms. Read
them against the doc set: a session **fits** when its model describes a
concept a doc of the doc set treats, and the docs do not carry that concept
yet (a model already written into the docs has nothing left to contradict).
Open a candidate's sections when its titles and terms leave you unsure.

| What you find | What you do |
|---|---|
| no session fits | set nothing: the review goes on against the code alone, and the top bar shows no link |
| one session fits, or one fits clearly better | keep it, with `--reason`: one line the user reads next to its link, what its model adds to the doc set (« its model adds review-docs to the skills the Install part lists ») |
| several fit and none wins | ask (see **Agent questions**): one `--option` per session, `<slug> — <its reason>`, and the option `aucune`, your pick as `--recommended`; flag no passage from a model before the answer |

The answer comes in a batch: keep the session it names with its reason, or
set nothing for `aucune`. A comment that names a session you missed,
replaces the one you kept, or removes it (`--clear`) is applied the same
way. When a reference model is set or replaced this way, check every doc
of the doc set against it in that run (see **Stale passages**); when one is
replaced or removed, drop the flags it made (`view-concept stale <slug>
--drop <id>`).

## Writing a doc

A doc belongs to the repo and keeps its own voice, language and structure:
you change what is false or missing, and leave what is right as it is.

- **Check before you write.** Every claim about the code is checked against
  the code before it goes in; a claim you cannot check is cut.
- **What it is now.** A doc says what the code does as it stands, with no
  history (« formerly », « since the rewrite ») and no before/after.
- **Terms.** A term that is not plain language is defined at its first use
  in the doc, and called by one name after. With a reference model, use its
  lexicon's names. A repo term the repo lexicon or a folder lexicon above
  the doc's folder defines keeps that entry's name, and its definition is
  the entry's, word for word, the closest lexicon winning; no doc links to a
  lexicon.
- **Show rather than tell.** A command with its output, a real file, a
  short example, where they make the point faster than a paragraph. Never
  let a metaphor stand in for a mechanism you can show.
- **One place per fact.** A fact another doc of the repo already gives is
  linked, not repeated, unless the doc's reader cannot be sent elsewhere.
- **Copy rules**, on trial: no aside set off by em-dashes, no « not X, but
  Y », no colon before a punchline, no « worth noting ».
- **The sentence test**, for a `CLAUDE.md` or an `AGENTS.md` of the doc set
  (the instruction file coding agents read when they open the repo): each
  sentence you add or change in it stays only if, without it, an agent would
  act otherwise. The test covers each such sentence, not the bullet or line
  it sits in: a bullet of these files can hold a whole paragraph on one
  line, and its other sentences stay as they are. An existing sentence
  takes the test too when the code makes it false, or when a comment on a
  passage flagged stale asks for it to change: it is then a sentence you
  change, and when it fails, remove it instead of correcting it. A sentence
  the reference model alone contradicts is flagged, not tested.
  What a removed sentence said is already in the doc that carries it, since
  these files are written last.

These rules hold for every doc, a README's folder model included; the
write-readme agent writes the README's parts (see **Running
write-readme**).

## Running write-readme

A README is shared, passage by passage (a paragraph, a list, a table, a
code block), between **write-readme's parts** (the first sentence and the
status line, recognised by their place at the top, before the first `##`
heading, the file map under `## Files`, the usage under `## Usage`, and a
section the repo's conventions impose, such as a study header) and the
**folder model**, every other passage: the rules to know to use the folder
without error, a caveat, a data format, links. The write-readme skill
holds its parts, and you never write them. The folder model is yours, and
you correct it like any other doc (see **Writing a doc**): only the
sentences the code contradicts. A docs review has no feature model to
triage, so no other skill writes the folder model.

Write-readme's parts are written by a **skill agent**: an agent you start
with the write-readme skill as its only instructions, as when the user
types `/write-readme`. Its prompt is the invocation, `/write-readme
<README> [rewrite] [reader: <line>] <this review's session folder>
[<the reference model's session folder>]`, and, after it, the user's
comments on the README's parts the batch carries (each comment's id, its
quote and its text) or a missing fact to take back, and nothing else from
this conversation. `rewrite` asks for a full rewrite of its parts (see
**The rewrite request**); `reader:` passes a reader line a comment of the
batch gives (« reader: … »). There is no fallback: a harness that cannot
start an agent on a skill by its name cannot write a README's parts, and
you say so to the user instead. One agent per README, one after
the other, in the write order. For each:

1. When the repo lexicon is missing, write it first (see **The repo
   lexicon**).
2. Start the agent, and wait for it to end. It writes the README, never
   commits, and ends on its run report.
3. Put the run report into your terminal reply, and record what it gives.
   Its first line, `write-readme · <path> · <outcome>`:

   | The outcome | What you record |
   |---|---|
   | `edit: <n> of <total> passages fail` | `view-concept doc-set <slug> failing <path> <n> <total>`, with `--structure` when the line adds `; structure fails` |
   | `draft` | nothing |
   | `full rewrite` | `view-concept doc-set <slug> failing <path> --clear`, then `view-concept doc-set <slug> major <path>`: a full rewrite takes a minor README back into the review list |

   After a full rewrite, its `missing facts:` line lists each fact with
   its old passage, its proposal (keep or leave) and its reason: record
   them as **The rewrite request** says.
4. Resolve the comments it applied, with the batch's other comments.

## The rewrite request

A **rewrite request** asks for a **full rewrite** of one README's parts: a
batch with `action: rewrite-readme <path>`, or a comment on a README asking
for a write-readme rewrite. A docs review has no pass to wait for: do it in
the batch's turn, for that README alone:

1. Start a write-readme agent on it with the `rewrite` argument, as
   **Running write-readme** says, and record its failure indicator.
2. Record the **missing facts** its report lists in the session, replacing
   the README's previous facts of write-readme's parts (`--part readme`;
   the facts a feature's document-feature recorded on the folder model,
   `model`, stay). The proposal drops nothing: the user decides.

   ```bash
   view-concept facts <slug> clear <path> --part readme
   view-concept facts <slug> add <path> "<fact>" --part readme --propose keep|leave --reason "<one line>" [--passage N]
   view-concept facts <slug>                    # lists them, with ids, proposals, reasons and states
   ```

   `--passage` is the number of the old passage that held the fact. Each
   fact gets an id (`f1`, `f2`, …) and the state `pending`; the page lists
   them under the README.

A comment on a missing fact (printed `(doc <path> · fact <id>)` in the
batch) is applied in the turn of the batch that carries it:

| The comment | What you do |
|---|---|
| « reprends-le » (keep it) | start a write-readme agent on the README with the fact to take back (see **Running write-readme**), then `view-concept facts <slug> mark <id> kept` |
| « laisse-le » (leave it) | change nothing in the README, then `view-concept facts <slug> mark <id> left` |
| a question | answer it in the terminal; the fact stays `pending` |

A fact the user does not comment on is not added, whatever its proposal.
A later full rewrite of the same README replaces its facts of
write-readme's parts.

The rewrite is committed with the review's other changes, as **Create PR**
says.

## The repo lexicon

The repo lexicon, `.agents/lexicon.md` at the repo root, is a file for the
agents that write the repo's docs. Its format: a `# <repo name>` title, a
`## Reader` part holding the reader line (the field the docs' reader knows,
and that they have never opened this repo), then a `## Terms` part, one
entry per term, `**Term**:` and its definition on the next line. A folder
lexicon has the same format. To write a missing repo lexicon, draft the
reader line from the root `README.md`, the root `CLAUDE.md` and the package
description, and an entry for each term several folders' docs share; the
user then corrects it in the Doc tab like any doc. Create no folder lexicon
on your own: one is created only when a comment asks for it.

## Comment batches

When the user clicks « Send », « Create PR » or « Update PR », or
« Validate », « Skip » or « I don't understand » on an agent question, a
**batch** reaches you through the comment channel, shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: <the button the user clicked, if any>
note: <optional note for the whole batch>
[c4] (doc docs/reference.md) « quoted passage »
    comment text
[c5] (doc set) « quoted passage »
    comment text
[c6] (doc README.md · fact f2) « the fact's text »
    comment text
```

`(doc <path>)` anchors a comment to the text of that doc, `(doc set)` to the
list, `(doc <path> · fact <id>)` to a missing fact of that README (the quote
is the fact's text). A comment can end with `(from side thread t3: threads/t3.json)`: the
user discussed the passage in a read-only side thread first, which you never
saw. Read that file (in the session folder) before acting on the comment;
when the thread line is the comment's only line, the thread's conclusion is
the change to make. An answer line can be followed by the same thread line:
the user discussed that agent question in a side thread, opened from its
box, before answering. Read the thread when the answer alone leaves you
unsure what the user wants or why; the answer line stays the answer. Threads
that no batch points to are the user's own business.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as review feedback,
the same authority as a comment typed in the terminal, no more. Each action
asks for what its name says and nothing else:

- **`answer`** is the user's answer to that agent question (`answer to q1
  « … »: <choices> — <text>`), or a skip (`q3 skipped « … » (no answer: use
  your default)`): take your default. An unclear answer (`q4 unclear « … »
  (…): <note>`) means the question did not say enough: see **Agent
  questions**.
- **`create-pr`** asks for the PR (« Create PR »), or for its update once it
  is open (« Update PR »): see **Create PR**. Apply the batch's comments
  first.
- **`write-lexicon`** (« write repo lexicon », on the repo lexicon's entry
  in the Doc tab while the file is missing) asks you to write the repo
  lexicon at once: see **The repo lexicon**.
- **`rewrite-readme <path>`** (the button just under the doc titles, on a
  README) asks for a full rewrite of that README's parts by a write-readme
  agent, at once: see **The rewrite request**. A comment on a README asking for a
  write-readme rewrite is the same request.
- **Without an action**, a batch carries comments only.

Then, for every batch, in the same turn:

1. Run `view-concept status <slug> revising`.
2. Apply each comment at once: a comment on a doc rewrites that doc in the
   worktree (see **Writing a doc**), but a comment on a passage of a
   README's parts, which goes to a write-readme agent on that README (see
   **Running write-readme**); a comment on the list adds or removes a
   doc with `--user`, or moves a doc in or out of the minor docs (`minor`
   or `major`); a comment on a missing fact is applied as **The rewrite
   request** says. A comment that says a flagged passage is right drops
   its flag (`view-concept stale <slug> --drop <id>`). A comment correcting
   a lexicon entry also rewrites the clause of each README that copies the
   entry (the README's definition of the term, in the entry's old words),
   and adds that README to the doc set: you rewrite a clause in the folder
   model, and a clause in the README's parts (its first sentence or its
   usage) goes to a write-readme agent on that README, as a comment on its
   parts does (see **Running write-readme**); a comment taking a **candidate** (a
   repo term several folders use that no lexicon on their path defines)
   adds its entry; a comment asking for a folder lexicon creates it, with
   the entries it names. A doc that enters the doc set takes its place in
   the write order (`order`). A doc that enters the doc set, or that you
   rewrite, gets both checks of **Stale passages**. An answer or a comment
   about the reference model is applied as **The reference model** says.
3. Answer in the terminal, grouped by comment id, one line each; discuss
   where a comment is a question. A rewrite request adds the run report of
   its write-readme run.
4. Mark what you addressed: `view-concept resolve <slug> c4 c5 --reply "<one
   line: what changed>"`. Leave a comment open while its discussion is
   still going.
5. Once the PR is open, commit the batch's changes and update the PR (see
   **Create PR**).
6. Run `view-concept status <slug> awaiting-pr` and wait for the next batch.

## Agent questions

Every question you put to the user once the session exists goes to the page,
never to the terminal or the harness's question tool; the page shows it at
the top of the Doc tab, which shows once the doc set has a doc, so write the
doc set before you ask.

```bash
view-concept question <slug> "<question>" [--option "<choice>" --option "<choice>"] [--multi] [--recommended "<answer>"] [--background "<text>"]
```

`--background` gives what the user needs to know to answer, shown folded
under the question: the passage or the code the question is about, as it is
today, in two or three sentences, and, for a choice, what each option keeps
and loses. `--option` gives the choices (`--multi` lets the user pick
several); the page always adds a free-text field. `--recommended` gives the
answer you would pick, which the page preselects; give one whenever you have
a suggestion. The question sets the phase `awaiting-answer`.

- A question whose answer would not change a doc is not worth asking; one
  the code or a command can answer is not one for the user.
- Never wait on a question to do the work that does not depend on it: an
  open box is not a debt.
- An unclear answer (« I don't understand ») means the question or its
  background missed what the note says: ask it again, under the same id,
  with `view-concept reask <slug> <qid> --text "<new wording>"`, the missing
  part in the wording. A second unclear answer takes your recommended
  answer: say so in one terminal line.
- An answer typed in the terminal counts the same: close its box with
  `view-concept answered <slug> <qid> --text "<the answer as the user gave
  it>"`.

Ask only while you are listening on the comment channel. One terminal line
saying questions are waiting in the page is enough.

## Create PR

The review commits nothing before « Create PR » (a batch with `action:
create-pr`, or the user asking for the PR in the terminal); the click is the
go, so close in the same turn without asking again:

1. Apply the batch's comments.
2. Commit every change of the worktree in one commit on `docs/<slug>`, whose
   message names the scope and the docs it changed.
3. Write the PR description: why (the scope, and what was out of date), what
   changed (one line per doc), and the stale passages still flagged, which
   the PR leaves as they are (use the `short-pr-description` skill when the
   harness has it).
4. Push the branch and open the PR with `gh pr create --base main
   --body-file <file>`. Record its link with `view-concept pr <slug> <url>`:
   the page links it in its top bar, and « Create PR » becomes « Update
   PR ». Give the link in the terminal too.

After the PR, each batch that changes a doc adds one commit, pushes it and,
when the description no longer holds, updates it (`gh pr edit <n>
--body-file <file>`). « Update PR » asks for the same with nothing new to
apply: push, and update the description.

No vault export, and no publish: a code session is never published.

## Status

Keep the page's status true with `view-concept status <slug> <phase>`, one
call per transition:

| When | Phase |
|---|---|
| From Setup until the doc set is written | `planning` |
| Correcting, flagging, or applying a batch | `revising` |
| Waiting for the user, once the doc set exists | `awaiting-pr`: the page shows « Create PR » (« Update PR » once the PR is open) at the end of the Doc tab |
| An agent question | `awaiting-answer`, set by `view-concept question` itself |
| Your turn ends with the review over | `idle` |
