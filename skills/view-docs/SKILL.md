---
name: view-docs
description: >-
  Review a repo's docs on a scope in the view-concept page, with no branch to
  model: list the docs the scope concerns, correct what the code contradicts,
  flag what another session's model contradicts, rewrite the docs on each
  comment batch, then open a PR on a docs branch of its own. Use when the
  user wants docs checked, brought up to date or rewritten — "review the
  docs about X", "are the install docs still right", "update the docs of
  this folder", invokes /view-docs.
argument-hint: "[the docs to review: a folder, files, or a subject]"
---

# /view-docs

Reviews a repo's docs in the view-concept page (the `view-concept` command):
the list of docs a scope concerns, each doc shown as it is in a worktree of
its own, corrected where the code contradicts it, then rewritten on the
user's comments until a PR carries it. You do the whole review yourself: no
other agent writes for it.

The scope to review is whatever the user typed after the command name: a
folder, a list of files, or a subject (« everything about the install »).
When it names another session's model to measure the docs against (« with
the model of doc-tab »), that is the reference model (see **Stale
passages**).

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
3. **The first run**: the stale passages the code contradicts corrected,
   those the reference model contradicts flagged.
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
    --kind code --repo <the worktree> --base main --workflow view-docs
view-concept reference <slug> <other slug>   # when the request names a reference model
view-concept open <slug>                     # starts the server if needed, shows the page
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
```

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
- a subject: every doc with a passage about it, wherever it sits.

The reason is one line the user reads in the list: what in the doc the scope
concerns (« the Install part: the Claude Code plugin, Jazz, Codex, the other
agents »), not why the rule let it in. Docstrings and code comments are not
docs and stay out. A doc outside the scope enters the doc set when a comment
asks for it.

## The Doc tab

The page shows the review in the **Doc tab**, the only tab of a docs review:
your open questions at the top, then the doc set, each doc with its reason
and its count of stale passages, then one doc at a time, read from the
worktree at each render, so your rewrites and the user's own edits show
alike. A doc carries two marks: the **base mark**, a blue bar in the right
margin of each block that differs from the same doc on `main` (the whole
text for a doc the review creates), so it shows at any time what the PR
will hold; and the green highlight of what changed since the user's last
batch. When the session has a reference model, the terms of its lexicon are
underlined in the docs with their definition on hover, and the top bar links
to its session. « Create PR » sits at the end of the tab.

## The first run

Once the session is open, in the same turn:

1. Write the doc set (see **The doc set**).
2. Run `view-concept status <slug> revising`, then look for the stale
   passages in every doc of it (see **Stale passages**): correct those the
   code contradicts, in the doc files, and flag those the reference model
   contradicts.
3. Ask what the reading left open (see **Agent questions**): a doc whose
   place in the scope you cannot tell, a correction that needs the user's
   call.
4. Run `view-concept status <slug> awaiting-pr` (the page shows « Create
   PR ») and say in one terminal line how many docs the doc set holds, how
   many passages you corrected and how many you flagged.

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
**reference model**, the model of another session of the same repo, a
branch review whose sections and lexicon say what the code now does or is
about to do. The user names it at launch or later in a comment; set it with
`view-concept reference <slug> <other slug>` (`--clear` removes it). Re-read
its `plan.json` (outline and lexicon) and its `sections/` in
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
doc you rewrite or add to the doc set, in the same run.

## Writing a doc

A doc belongs to the repo and keeps its own voice, language and structure:
you change what is false or missing, and leave what is right as it is.

- **Check before you write.** Every claim about the code is checked against
  the code before it goes in; a claim you cannot check is cut.
- **What it is now.** A doc says what the code does as it stands, with no
  history (« formerly », « since the rewrite ») and no before/after.
- **Terms.** A term that is not plain language is defined at its first use
  in the doc, and called by one name after. With a reference model, use its
  lexicon's names.
- **Show rather than tell.** A command with its output, a real file, a
  short example, where they make the point faster than a paragraph. Never
  let a metaphor stand in for a mechanism you can show.
- **One place per fact.** A fact another doc of the repo already gives is
  linked, not repeated, unless the doc's reader cannot be sent elsewhere.
- **Copy rules**, on trial: no aside set off by em-dashes, no « not X, but
  Y », no colon before a punchline, no « worth noting ».

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
```

`(doc <path>)` anchors a comment to the text of that doc, `(doc set)` to the
list. A comment can end with `(from side thread t3: threads/t3.json)`: the
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
- **Without an action**, a batch carries comments only.

Then, for every batch, in the same turn:

1. Run `view-concept status <slug> revising`.
2. Apply each comment at once: a comment on a doc rewrites that doc in the
   worktree (see **Writing a doc**); a comment on the list adds or removes a
   doc with `--user`. A comment that says a flagged passage is right drops
   its flag (`view-concept stale <slug> --drop <id>`). A doc that enters the
   doc set, or that you rewrite, gets both checks of **Stale passages**.
3. Answer in the terminal, grouped by comment id, one line each; discuss
   where a comment is a question.
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
