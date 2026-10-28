---
name: build-feature
description: >-
  Build a feature in the view-concept page, concepts first: model what the
  feature introduces and how it fits the existing code, challenge and revise
  the model with the user, send agents to bring the code in line with it,
  check the code item by item against it, then write the docs and open the
  PR. Use when the user wants to design, build, understand or rework a
  feature on a branch — "let's build this feature", "work on this branch",
  "review my branch", "explain this branch so I can decide what stays",
  invokes /build-feature.
argument-hint: "[the branch or PR number]"
---

# /build-feature

Builds a feature in the view-concept page (the `view-concept` command): a
model of what the feature introduces, written and corrected with the user,
agents that change the code on its branch to match it, a check of the code
against the model, then the docs and the PR.

The tool is self-contained: the model is built for this branch and lives in the
session; it reaches the repository only through the **doc pass**, which
carries it into the repo's docs before the PR.

The branch to review is whatever the user typed after the command name (the current branch when nothing).

## The model

The **model** of a branch is the set of concepts it introduces or changes. A
**concept** is an object, a rule, a format or a name the code relies on: « a
cohort is the group of speakers a recording comes from », « a gate drops a
segment when its silence ratio exceeds the threshold », « `prepared/` holds one
folder per dataset ». For each concept, the model says what it is, the rules it
obeys, and how it relates to the concepts that existed before the branch.

A UI element, a file, a function or a table row is not a concept: it is where
a concept is implemented. « a row of the review table » is a part of a page;
the concept behind it is what the row stands for (« an item is one unit of the
diff that gets a verdict »). Name the concept; name the part only to say
where it lives.

The model is written for the user, who asked for the branch: it never tells
them back what they stated, and spends its text on what is new to them (what
the code does that they did not say, the decisions made for them, the
consequences). Its first section, the **model sheet**, gives an intuitive
view of the change, graphical where it can be, that lays out the subjects of
the sections after it. The work that fails the **section test** goes in the
**to-do list**, the section `todo`: the writer writes it with the model, but
it sits in the refactoring part (`"part": "refactoring"`, the part's first
entry), so the page shows it at the top of the code tab, next to the code
that carries it. Each default taken for the user, a skipped question's or a
listed default (a decision that changes nothing they see, do or risk, which
no question asks), is one « Default taken » line at the end of the section
it touches, never a list on the model sheet, and never stated in the
prose too. A section stays in the model only when it holds a decision the user makes or must make, or a consequence
they will notice; anything else is one line of the to-do list, which the
implementer carries and the reviewer checks.

In the page, the model is the outline and the lexicon of `plan.json` (one
entry per term that is not plain language, `kind` + `definition` + `tip`: a
**core concept** the model introduces or changes, or a **peripheral
concept**, any other term, which gets its tip only), and the **modeling part** of the
review: the sections that write the model out, which the page shows in the
Model tab. Every change of the model is logged in the **change history**
(`change-history.json`), one entry each: a concept added, removed, renamed,
merged or split, a rule or a relation changed, a section added, moved or
removed. A wording fix that leaves the model as it was gets none.

## The page

The page shows the review and sends the user's comments back to you; the
terminal only drives the conversation. A **session** is the review, stored as
plain files in `~/.view-concept/sessions/<slug>/` (the **session folder**).
The agents write the outline, the lexicon and the sections there, and the
page re-renders within a second of each write; nobody touches the page
itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands).

### Setup

A code session opened on the branch, with the user's first message verbatim
as the initial request and the branch it is compared with (the slug is a
short kebab-case name of the branch):

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the message>" \
    --kind code --repo <repo root> --base <base branch> --workflow build-feature
view-concept request <slug> <file>   # when the review follows a conversation
view-concept open <slug>          # starts the server if needed, shows the page
```

When the review follows a conversation about the feature, write its
**request transcript** right after `new`: every message of it, the user's and
yours, word for word and in order, from the first message about the feature
(leave out earlier messages on another subject), each under a `## User` or
`## Agent` heading, messages only (no tool call, no tool output). The
command writes it to `request.md` in the session folder, and replaces it
when run again. The planner and the writer read it whole; the implementer,
the reviewer and a side thread get its path and open it when a comment needs
the user's reasons. A review started with a single message has no
transcript: that message is its whole request.

The page runs side threads on the agent you are. Claude Code and Codex are
detected; any other agent (Jazz, …) adds `--agent jazz --agent-name <your own
agent name>` to `new` and to every later `open`. After resuming in a new
conversation, run `view-concept open <slug>` again, and `view-concept pending
<slug>` to list the comments still open.

### The comment channel

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

### Batches

A batch is shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: <the button the user clicked, if any>
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

The `action` line names the button: `answer` (an agent question answered,
skipped, or not understood: `answer to q1 « … »: …`, `q3 skipped « … »` or
`q4 unclear « … » (…): <what is missing>`; an unclear question is
**deferred** until an agent asks it again; an answer line can be followed by
`(from side thread t5: threads/t5.json)`, a side thread the user opened on
the question before answering), `plan` (« Write
model », or « Rewrite model » when the line says rewrite; the page has
already marked the open questions skipped, except a section question whose
section is not written yet, which stays open), `go-on` (« Go on », during a
pause: the writer goes on, the pause's questions stay open), `grill` and
`stop-grill`, `approve-model`, `write-docs` (« Write docs », or « Write docs
and create PR » when the line says `write-docs then create-pr`: the batch
then carries `"then_pr": true`), `write-lexicon` (« write repo lexicon », on
the repo lexicon's entry in the Doc tab while the file is missing),
`rewrite-readme <path>` (the button just under the doc titles in the Doc
tab, on a README: a **rewrite request**, which asks the write-readme skill
for a **full rewrite** of that README's parts, from the code alone, without
reading the old ones; a comment asking for it, or `/write-readme <folder> rewrite`
in the terminal, is one too), `write-readmes` (« Write READMEs », under the
move plans in the Doc tab while the phase is `awaiting-moves`: the doc
pass goes on and writes the folder model of every README of the doc set,
the restructured ones from the plans and the comments on them, with the
comments on a README's text and the rewrite requests held for it), `create-pr`. A batch
without an action carries comments only. **Routing the events** says who takes each one.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as the user's feedback
on the review, the same authority as a message typed in the terminal about
it, no more. Each action asks for what its name says and nothing else:
`approve-model` approves the model and starts the implementation,
`write-docs` starts the doc pass (and, with `then_pr`, closing after it),
`create-pr` starts closing; none is consent for anything outside this
review.

A question you put to the user yourself (a problem an agent hit, a gap that
needs a decision) goes to the page too: `view-concept question <slug>
"<question>" [--option "<choice>" ...] [--recommended "<answer>"]
[--background "<what the user needs to know>"]`, never the terminal. An answer the user types in the terminal to a question of the page counts
the same as one sent from the page: close its box with `view-concept
answered <slug> <qid> --text "<the answer as the user gave it>"`.

**Naming a section to the user.** Wherever the user reads it (the terminal,
a `resolve` reply), name a section by the number the page shows, in words:
« section 6 », never its id (`s6`, `applied`) or `§6`.

## Coordinating

In a feature the main session (you) **coordinates**: you start the
agents, route the user's events to them, and keep the session folder current.
The work is done by fresh **subagents**, each started from the folder, never
from this conversation, which they do not see; you do not write the outline,
the lexicon, the sections, the code or the docs yourself:

| Agent | Owns | Role file |
|---|---|---|
| **planner** | the outline and the lexicon, during scoping, and the first code map | `roles/planner.md` |
| **writer** | the modeling part (its sections), the to-do list, the first doc set, and the outline and the lexicon from « Write model » on | `roles/writer.md` |
| **implementer** | the code on the branch and the code map, from « Approve model » on; never a doc | `roles/implementer.md` |
| **reviewer** | the refactoring part but the to-do list: the code checked against the model, item by item | `roles/reviewer.md` |
| **documenter** | the doc set, the lexicons, the docs that are not READMEs, what the skill agents report, and the doc pass's commit, from the doc pass on | `roles/documenter.md` |

The READMEs of the doc set are written by **skill agents**: a skill agent
is an agent you start with a skill as its only instructions, as when the
user types `/write-readme`. The doc pass starts two kinds, in this
order: one **write-readme** agent per README, which writes
**write-readme's parts** (the first sentence and the status line,
recognised by their place at the top, the file map under `## Files`, the
usage under `## Usage`, and a section the repo's conventions impose, such
as a study header), then one **document-feature** agent, which reads that
boundary by the headings and writes the **folder model** of each README
(every passage outside write-readme's parts). No role
file and no skill sends an agent to read another skill.

The **code map**, `code-map.md` in the session folder, says which modules
carry the feature and where each concept lives, so a fresh agent does not
explore the same code again: the planner writes it on its first run, the
implementer updates it when it moves code, and every context loads it.

The role files are in `~/Documents/code/view-concept/skills/build-feature/`.
The planner and the writer also read `roles/planning-rules.md` there. A side
thread the user opens from the page is one more agent, read-only, which the
server starts itself from the same folder.

### Starting an agent

Each run starts from the output of

```bash
view-concept context <slug> --role <planner|writer|implementer|reviewer|documenter> --trigger <ids or words>
```

It prints the **base context** (the initial request, or the request
transcript for the planner and the writer, the outline, the
lexicon, the code map, the recent change history, the questions, the recent
terminal messages, and the sections the role needs) and the **trigger**: the events
that started this run, in full. Once the model is approved, it also says up
to which change of the model the code is implemented, and lists the changes
**not implemented yet**.

Hand the context over **by command**: give the new subagent the command, never
its output, and let it run the command itself. Its prompt is: « Run
`view-concept context <slug> --role <role> --trigger <ids or words>` and treat
its output as your context. Then read `<role file>` (and
`roles/planning-rules.md` for the planner and the writer) in
`~/Documents/code/view-concept/skills/build-feature/`, and do your run. » Do not
run the command yourself first, save its output to a file, or paste it into
the prompt: the context grows with the session (a writer's holds every
section), and it would go through your own conversation, where it stays, and
be typed out again. Start it as an agent that can write files and run
commands, never a read-only type: each role file says what that agent may
change, and nothing beyond it. Nothing else from this conversation: what the
agents need is in the folder. When the run ends, give its one-line report in the
terminal.

The session may run a **variant**, a named setup with a model per role, which
`view-concept variant <slug>` prints (run it when you open or resume the
session). When the variant sets a model for a role, start that role's agent
with it as the Agent tool's model; a role it leaves out gets no model, and
keeps yours. Its helpers then take its model.

You start the role agents. A role agent may in turn start **helper agents**,
one per part of its run, so the parts are done at once; its role file says
when and how:

| Role | A helper's part |
|---|---|
| reviewer | one item, or a few small items grouped |
| implementer | a set of files no other part touches, in its own git worktree, when at least two such sets are each more than a small fix |

The planner and the writer start none: the writer writes its sections one
after the other, each from the text of the sections before it. A helper
never starts one itself. Every helper
obeys the **owner rule**: it writes only its own section file (or, for the
implementer, its own code files), and returns everything else (lexicon terms
and tips, outline moves, changes of the model, item fields, questions, what
moved in the code) to the role agent that started it, which writes them
alone, after its helpers end. The shared session files (`plan.json`, the
change history, the questions) are rewritten whole by each command that
writes them, with no lock, so two helpers writing them would lose each
other's work.

A harness without subagents runs each run itself, one after the other, from
the same context command and role files, and a role agent's helpers the same
way.

### Starting a skill agent

A skill agent starts from no context command and no role file: its prompt
is the skill's invocation, the skill's name and its arguments, as the user
would type them, and nothing else from this conversation:

- write-readme: `/write-readme <README> [rewrite] [reader: <line>]
  <session folder>`, one README; `rewrite` for a full rewrite of its parts
  (see **The doc pass**), and `reader:` when a comment of the batch gives
  a reader line (« reader: … »);
- document-feature: `/document-feature <session folder> <README> ...`,
  the READMEs of the doc set, in the write order.

Add, after the invocation, the user's comments the agent must apply (each
comment's id, its quote and its text, as the batch printed them), and,
for a fact to take back, the fact and its README. There is no fallback:
a harness that cannot start an agent on a skill by its name cannot run the
doc pass, and you say so to the user instead. A skill agent writes the README and the session
files its skill names, and never commits: the documenter commits its work.
Give its run report, the last message it prints, in the terminal as it
printed it, and keep it for the documenter's trigger.

### Routing the events

The user's **events** are what reaches you: a batch from the page (an answer,
a skip, comments, a button), or a message typed in the terminal. Each event
starts one pass. Who takes it depends on the stage:

| Event | During scoping | After « Write model » | After « Approve model » |
|---|---|---|---|
| an answer (`action: answer`) | planner | writer | the agent that asked it |
| a skip | nothing: the outline already used the default | the writer, when it answers a pause; nothing otherwise | nothing |
| an unclear answer | planner | writer | the agent that asked it |
| comments with no action | planner | writer; a comment on a doc's text waits for the doc pass | by section: the modeling part and the to-do list to the writer, the rest of the refactoring part to the reviewer; the doc set list to the writer before the doc pass, to the documenter after; the text of a doc that is not a README, or a missing fact, to the documenter; a README's text to the skill agent holding the passage, then to the documenter (see **The docs after the doc pass**); a row of the concept triage to a document-feature agent, then to the documenter; a doc's text waits for the doc pass when it has not run; a row of a move plan or a README's text is held for « Write READMEs » while the phase is `awaiting-moves` |
| a terminal message about the feature | record it, then planner | record it, then writer | record it, then the writer if it is about the model, the implementer if it asks for a code change |
| an answer to a page question typed in the terminal | `view-concept answered`, then planner | the same, then writer | the same, then the agent that asked it |
| « Rewrite model » (`action: plan`, the line says rewrite) | — | writer | writer |
| « Go on » (`action: go-on`) | — | writer | — |
| « Grill me » (`action: grill`) | planner | writer | writer |
| « Write model » (`action: plan`, the line says write) | see **Model consolidation** | — | — |
| « Approve model » (`action: approve-model`) | — | see **Model consolidation**, step 7 | — |
| « Write docs » (`action: write-docs`) | — | — | see **The doc pass** |
| « Write READMEs » (`action: write-readmes`) | — | — | the doc pass goes on, with the comments on the move plans, on a README's text and the rewrite requests held for it (see **The doc pass**, steps 4 and 5) |
| « write repo lexicon » (`action: write-lexicon`) | — | held for the doc pass | documenter, held for the doc pass when it has not run |
| a rewrite request (`action: rewrite-readme <path>`, a comment asking for a README to be rewritten, or `/write-readme <folder> rewrite` in the terminal) | — | held for the doc pass | a write-readme agent with `rewrite`, then the documenter; held for the doc pass when it has not run, for « Write READMEs » while the phase is `awaiting-moves` |
| « Create PR » (`action: create-pr`) | — | — | see **Closing** |

The agent that asked a question is the one whose report counted it; when you
cannot tell, give it to the writer.

Record a terminal message about the feature with
`view-concept message <slug> "<the message, as the user wrote it>"` before
anything else: the agents never see the terminal. Process messages (« go
ahead », « stop ») are not recorded.

**One agent at a time.** While an agent runs, queue the events that arrive.
When it ends, start the next run with every queued event in its trigger,
not one run each. Pass the trigger as the ids the context command resolves:
question ids (`q3`), comment ids (`c7`), a batch id (`b4`) for a whole
batch, terminal message ids (`tm2`), change ids (`m7`), section ids (`i3`); a
button that carries nothing else goes in words (`"« Write model »"`), and so
does an agent's report you pass on (`"implementer report: <the line>"`).

« Stop grill » (`action: stop-grill`) starts nothing: the next runs no longer
see a grill in their context.

### Status

Keep the page's status true: `view-concept status <slug> scoping` from Setup
to « Write model », and after each writer run `view-concept status <slug>
awaiting-model` when no question it asked is open, every section of the
modeling part and the to-do list are written, and `audit.json` holds no entry with `"issue":
"undefined"`. A writer paused on its questions sets the phase
`awaiting-answer`, which the page reads as the pause, as step 5 says; a
question « Go on » left open, still open once every section is written,
keeps that phase too: « Approve model » waits until each is answered,
skipped or deferred.

The third condition is the **undefined gate**: the writer clears every audit
underline itself, so « Approve model » never shows with an « audit ·
undefined » underline on the page. When one is left, start the writer again
with the trigger `"audit: undefined entries left"` before setting the phase.
The gate is a rule you and the writer follow: `view-concept status` itself
refuses nothing.

After « Approve model », set the waiting phase at the end of each pass, when
no question is open: `view-concept status <slug> awaiting-docs` until the doc
pass has run (the page shows « Write docs » and « Write docs and create PR »),
`awaiting-moves` when the doc pass stopped on a move plan (the
document-feature agent's report says `move plan waiting`; the page shows
« Write READMEs » under the move plans), `awaiting-pr` after it (the page shows « Create PR »). The agents set the rest
themselves: the planner `scoping --done` when it leaves no question open, and
the writer or the reviewer `writing` once at the start of each run of
sections, naming them (`--section <id>`, repeated) unless it writes every
section with no file yet. The page reads from the section files which
section is being written and how many are done.

## The flow

The review runs in two steps: **model consolidation** (the model is written
and corrected with the user) and **implementation** (the implementer makes
the code carry the model, and the reviewer checks the code against it, item
by item).

A review is a list of **sections**: plan.json lists them under its `outline`
key, and `sections/<id>.md` holds the text of each. The sections fall in two
parts. The **modeling part** writes the model out; the page shows it in the
Model tab (the page's name for the Explanation tab in a feature). The
**refactoring part** checks the code against the model; a section with
`"part": "refactoring"` belongs to it, and is a **refactor section**: the
page shows it in the code tab. The to-do list (`todo`) is the one refactor
section written with the model, and the page shows it first. An outline entry holds a short,
high-level title (the subject or the point) and its `earns`, the one
sentence the user reads under the title in the page (at most 200
characters): no notes for the writer, who works from the same outline.

### The visual rule: Markdown or HTML

A section may be written as an **HTML section**: `sections/<id>.html` instead
of `sections/<id>.md`. The page draws it in a frame of its own, as claude.ai
draws an artifact: its scripts run, its styles stay inside the frame, and it
can load from the web. The extension alone says the kind; a section has one
file, so delete the `.md` when you switch a section to HTML (`view-concept
check` reports a pair).

- **When.** The user prefers to be shown rather than told: whenever a
  section has something to show, write it as an HTML section. Something to
  show is a mockup of a page or an output (the box as the user will see it), a
  flow over time (a step player through a run), a state machine (a question
  going from open to deferred to answered), a before/after, or a comparison
  the reader can play with (two options side by side). Write a Markdown
  section when the section is an argument, a definition or a rule, with at
  most a small table: a visual that only repeats the prose is not relevant.
  Nor does the prose repeat a visual: no paragraph tells what a figure
  shows, and a caption says only what the figure cannot.
  A Mermaid block is for a plain structure in an otherwise prose section (a
  short sequence, a tree), not a substitute for showing the thing itself.
  Never write an HTML block (raw HTML that starts its own paragraph) into a
  Markdown section: `view-concept check` reports it; inline HTML in a
  sentence (`<b>`, `<span>`) is fine.
- **What the file holds.** One self-contained HTML document: its HTML, CSS and
  JavaScript in the file, no heading of its own (the page renders the title).
  Paint with the page's theme tokens, `var(--bg)`, `var(--ink)`,
  `var(--ink-dim)`, `var(--muted)`, `var(--line)`, `var(--raised)`,
  `var(--accent)`, `var(--ok)`, `var(--warn)`, `var(--flag)`, `var(--danger)`,
  `var(--info)`, `var(--alt)` and `var(--mono)` for the font: the frame
  receives them and follows the page's light or dark theme, so never hard-code
  a palette.
- **Width.** The frame is wider than the text column of a Markdown section: up
  to 120 characters of the page's font (about 1000px), narrower in a small
  window, about 340px on the published page's phone layout. Lay figures out to
  use that width (two panels side by side, a long timeline), and make the
  section read in a 340px frame too, with nothing cut off and no sideways
  scroll but a table's own: a row of panels sets a minimum width per column
  (`repeat(auto-fit, minmax(min(100%, 16rem), 1fr))`), never a column count.
  Prose keeps the page's text width, and the frame sets it: write a paragraph,
  list or quote as `<p>`, `<ul>`, `<ol>` or `<blockquote>` straight in the
  `<body>`, and a caption as a `<figcaption>` (inside the `<figure>` it
  captions); the frame caps each at 78 characters and centres it, as in a
  Markdown section. Text in a `<div>` of your own runs the frame's full width.
- **Base style.** The frame gives every section the Markdown section's font
  (`var(--mono)`), size and line height, three named sizes, `var(--fs-body)`
  (14px), `var(--fs-small)` (12px) and `var(--fs-label)` (11px), and the table
  look to every table (borders, a header fill, small text, a sideways scroll
  when wider than the frame). Set no body size or table style of your own; a
  rule you write still wins over the base style, property by property.
- **Component kit.** The base style defines these classes in every frame:
  reuse them instead of inventing your own, so repeated siblings share one
  class.
  - `.label`: a small uppercase, letter-spaced label; it may open a panel, a
    pair's child or a callout.
  - `.chip`: an inline tag on a neutral fill.
  - `.panel`: a block on a fill, with no border.
  - `.pair`: a before/after, `<div class="pair"><div class="before">…</div>
    <div class="after">…</div></div>`, before always first (left, or above
    once the columns wrap).
  - `.steps`: an ordered timeline, `<ol class="steps"><li>…</li></ol>`.
  - `.callout`: a left bar on a light fill, for a verdict.
  - `.defaults`: the defaults taken, closing a section: a `.label` header,
    then one `<p>` per default, ruled apart:
    `<div class="defaults"><div class="label">defaults taken</div><p>…</p></div>`.
  - `.tabs`: alternatives, one panel shown at a time. The n-th `.tab` shows
    the n-th `.tab-panel`; the others carry `hidden`:

    ```html
    <div class="tabs">
      <div class="tab-row">
        <button class="tab" aria-selected="true">Option A</button>
        <button class="tab">Option B</button>
      </div>
      <div class="tab-panel">…</div>
      <div class="tab-panel" hidden>…</div>
    </div>
    ```

    Write no script: the frame runs the tabs, and opens the tab or
    `<details>` that holds a passage a comment, a side thread or a change
    points to.
- **Design rules.**
  - Short table cells (a name, a number, a few words), and code references
    (`path:line`, a function) in one column of their own.
  - A border, a fill or a shadow only on the element that must stand apart:
    on every block, nothing stands apart.
  - Metadata (a status, a kind, a column name) in a `.label`.
  - No table for a layout: a to-do list or a grid of panels is a list or a
    grid of `<div>`s, since every table reads as a data table.
  - Only the three named font sizes.
  - Siblings spaced with their container's `gap`, never a margin per child.
  - Numbers only where the order is real: a number, a label above a heading
    or a divider says something true about the content.
  - Alternatives and long lists in `.tabs` or a `<details>`.
- **Size.** Under 2 MB, embedded media included. Never write a large image or
  video into the file as a data URI: load it from the web or, when you
  produced it yourself (a manim render, a GIF), put it in the section's media
  folder, `sections/<id>/`, and load it by a relative address (`<video
  src="<id>/step-1.mp4">`). The page serves the folder, and the published page
  and the vault export copy it along. `view-concept check` reports a file over
  the limit.
- **Loading from the web.** Libraries from cdnjs.cloudflare.com,
  cdn.jsdelivr.net or unpkg.com; any other site when the section needs it.
  Either way, a section that loads from the web needs a connection to show.
- **Prose.** No preference: an HTML section may hold prose as well as visuals,
  as an artifact does; choose how much goes there. A **visual-carried
  section** is one whose interactive visual makes its point alone (a hover
  demo, a step player, a before/after to click through): its prose shrinks
  to what the visual cannot show, often a sentence or two. Know its one cost: text a
  script paints into a `<canvas>` cannot be selected, highlighted or
  underlined, so a figure drawn there is commented as a whole. Everything else
  works as in a Markdown section: term underlines and their tips, change
  highlights, comments and side threads on a passage. Its visible text (outside its scripts and styles) still
  counts for `view-concept check`.

### The doc set and the Doc tab

The **doc set** is the list of the repo's doc files the branch concerns, each
with a one-line reason it is listed. It lives in `doc-set.json` in the
session folder, and the agents write it only through `view-concept doc-set`,
never by hand:

```bash
view-concept doc-set <slug>                                 # prints it
view-concept doc-set <slug> add <path> "<reason>" [--user]  # adds a doc, or changes its reason
view-concept doc-set <slug> remove <path> [--user]          # removes a doc
view-concept doc-set <slug> order <path> <path> ...         # puts the doc set in the write order
view-concept doc-set <slug> minor <path> "<reason>" --added N --removed N  # classes a doc minor
view-concept doc-set <slug> major <path>                    # takes the minor class off
view-concept doc-set <slug> failing <path> <fail> <total> [--structure]  # records a README's failure indicator
view-concept doc-set <slug> moved <path> <old path>         # records a README the code moved with its folder
view-concept facts <slug>                                   # prints the missing facts, by README
view-concept triage <slug>                                  # prints the concept triage
view-concept moves <slug>                                   # prints the move plans, by README
```

A path is relative to the repo root and may name a doc the branch will
create. `--user` marks a change the user asked for in a comment: a doc the
user removed is recorded as removed, and `add` refuses it from then on unless
the user asks for it back (`--user` again). No agent adds back a doc the user
removed.

A doc enters the doc set by six rules, rules 1, 2 and 6 read from the diff,
rules 3 and 4 found by reading, rule 5 always applied:

1. a doc the branch already changed. A file the branch only moves, its text
   unchanged, does not enter by this rule: rule 2 covers the move;
2. the `README.md` of the folder that holds a **structural change**: a folder,
   or a file its README lists (an entry script, a study, a module), that the
   branch adds, removes, renames or moves. The README enters whether or not
   it mentions the change yet, since the change it misses is what this rule
   catches; one level up only, not to the repo root. A **content change**
   (an import, a refactor, a fix inside a file whose role stays the same)
   brings in no README by being next to it, and no `CLAUDE.md` enters by
   being next to a change: only rules 1, 3 and 4 bring them in;
3. a doc that cites a path the branch moves, renames or removes, or that
   describes something of a file the branch changes in the way the doc shows
   it: a command, its arguments, an output format, a name others import. A
   file whose inside alone changes brings in no doc that cites it;
4. a doc that describes a concept of the model;
5. the **repo lexicon**, `.agents/lexicon.md` at the repo root (the reader
   line, the field the docs' reader knows, and one definition per term the
   repo's folders share), always, present or missing, and each **folder
   lexicon** (a `.agents/lexicon.md` below the root, for the terms only the
   folders under it share) above a folder the branch touches. A missing
   repo lexicon is listed so its entry in the Doc tab carries « write repo
   lexicon »; no agent writes it unless that button, a rewrite request or
   a doc pass whose doc set holds a README asks for it;
6. the `README.md` of each folder the branch creates and of each folder that
   holds a structural change (rule 2's folder), present or missing. A
   missing README is listed under its path, and the doc pass writes it: the
   write-readme agent writes the **draft** of its parts from the code, and
   the document-feature agent adds a folder model after them when it has a
   concept to put there.

Before the code exists, a path the branch touches is where the model will
land, which the code map says. Docstrings and code comments are not docs and
stay out of the doc set.

Two agents keep it, at the two moments it changes: the **writer** writes the
first one with the model and corrects it on the user's comments until the
doc pass; the **documenter** refreshes it on the real diff at the start of
the doc pass (see **The doc pass**) and keeps it from then on.

The page shows the doc set in the **Doc tab**, after the code tab, once it
exists: the list, each doc with its reason, in the doc set's order (the
write order once the doc pass has recorded it), then one doc at a time, read
from the worktree at each render, so the user's own edits and the agents'
rewrites show alike. The lexicon terms are underlined in each doc. A doc
carries two marks: the **base mark**, a blue bar in the right margin of each
block that differs from the same doc on the base branch, with a blue
background on the words it adds (the whole text for a doc the branch
creates), and the green highlight of what changed since the user's last
batch. The user may also edit a doc by hand in the page, which writes the
file in the worktree: read a doc again before rewriting it, and keep the
user's edits. The user comments on a doc's text as on a section, and the
batch prints the comment with the doc's path in place of a section
(`[c12] (doc docs/reference.md) « … »`); a comment on the list prints
`[c13] (doc set) « … »`, a comment on a missing fact (below) prints
the README's path and the fact's id, `[c14] (doc README.md · fact f2)
« … »`, a comment on a row of the concept triage `[c15] (triage k2) « … »`,
and one on a row of a move plan `[c16] (moves benchmark/README.md ·
passage p3) « … »`.

At the top of the Doc tab, above the list, the **concept triage**: one row
per concept of the model, whether it enters the docs and why, which the
document-feature agent writes in the doc pass. A comment on a row goes to
a document-feature agent, which changes it and rewrites the folder models
it touches. Under it, one **move plan** per README the doc pass
restructures (passages must leave it): each passage, the README it goes
to, and what it becomes there; « Write READMEs » shows under the plans
while they wait.

At the end of the doc pass, the documenter classes as a **minor doc** each
doc it touched only for a detail with no effect on its meaning, with a
one-line reason and the doc's diff size in the doc pass commit; a doc it
creates is never minor, and before the doc pass no doc is. The list shows
first the **review list**, the docs the user is asked to read, then a fold
of the minor docs, each with its reason and `+added −removed`; the title
bar puts them after the review list, set back. A minor doc still opens,
takes comments and edits, and carries its marks. The reviewer reads it too,
and a stale passage on it puts it back in the review list, as does a
missing fact of it still `pending`. A comment on the list moves a doc
either way.

The write-readme skill always **edits** an existing README: only the
passages that fail its checks change. Beside each README it edited, the
list shows its **failure indicator**, « n/total failing », the share of its
passages that failed before the edit, with a mark when its structure fails
(which an edit does not correct); the documenter records it from the
write-readme agent's report with `view-concept doc-set <slug> failing`. Past half the passages, or with the
structure failing, the page puts the rewrite button forward: the user
decides. A **full rewrite** happens only on a rewrite request, or on a
README whose folder changes role (`role change` in the document-feature
agent's report). write-readme holds only its parts of a
README (the first sentence, the status line, `## Files`, `## Usage`, a
section the repo's conventions impose); every other passage is the
**folder model**, which the document-feature skill holds. After a full
rewrite by write-readme, a folder model document-feature rewrote whole, or
a restructuring, the skill agent lists the **missing facts**, each fact the old
README said that no README written says any more, in words or by a link,
recorded on the README the old file became, with the agent's
proposal (`keep` or `leave`) and a one-line reason: document-feature
records its own, and the documenter those of write-readme's report
(`view-concept facts`), and the Doc tab lists them under the README,
each with its state (`pending`, `kept` or `left`). The user comments on a
fact as on a passage: « reprends-le » and the skill agent of its part adds
it to the README, « laisse-le » and the README stays as it is; a fact no comment
names is not taken back.

### Model consolidation — the modeling part

1. **Setup.** Run **Setup**, arm the comment channel, and set `status <slug>
   scoping`.
2. **First planner run**, no trigger: it reads the docs and the code, drafts
   the outline and the lexicon, and asks the first questions in the page.
3. **The scoping loop.** Each event goes to the planner, as **Routing the
   events** says. When a run asks nothing and no question is open, say in one
   terminal line that the planner has no question left, and wait.
4. **« Write model ».** Scoping ends when the user ends it, never when an
   agent judges it has enough: a batch with `action: plan` while no section
   is written, or « go ahead » in the terminal. The open questions are marked
   skipped, except the section questions, which stay open until their section
   is written; the deferred ones stay deferred, to be asked again after their
   anchor section. Let the planner run first if events are still queued, then start
   the writer with the trigger `"« Write model »"` and the batch id. From here
   the writer owns the outline and the lexicon too.
5. **The pauses.** The writer writes the model one section at a time, in
   outline order, and stops after a section that has questions to ask (a
   deferred question anchored to it, a decision it makes answerable, or a
   section question still open and anchored to it): its report says
   « paused after section N ». Run `view-concept status <slug> awaiting-answer`, the phase
   the page reads as the pause (it shows « Go on » only then), say so in one
   terminal line and wait. The answers, skips and
   unclear answers go to the writer, which goes on writing from there. « Go
   on » ends a pause without answering: from the page (a batch with `action:
   go-on`, shown under the paused section's questions and in the scope block
   in place of « Rewrite model »), it starts the writer with the batch id; in
   the terminal (a process message, not recorded), with the trigger `"go
   on"`. Either way the open questions of the pause stay open.
6. **The discussion loop.** Once every section is written, each event goes to
   the writer. Set `awaiting-model` after each run, as **Status** says.
7. **« Approve model ».** Model consolidation ends when the user approves the
   model: a batch with `action: approve-model`, or saying so in the terminal.
   Approving also means « start the implementation »: when the batch carries
   comments, run the writer on them first, then go to **Implementation** in
   the same turn, without asking again. Approving ends a grill still running.

### Implementation — the code and the refactoring part

After « Approve model », each pass runs the agents in this order, skipping
those with nothing to do:

1. **The writer**, on the events about the model (comments on the modeling
   part, answers to its questions, « Rewrite model »). Each change of the
   model it logs is a change not implemented yet.
2. **The implementer**, when there is code to change. Its trigger holds:
   - « Approve model », on its first run: make the code carry the whole
     model;
   - the changes not implemented yet (`view-concept implemented <slug>`
     lists them);
   - the items the reviewer judged `diverges` or `move` in its last report;
   - the comment ids that ask for a code change.

   It starts one run for all of it; it splits the work across helpers when
   at least two parts with disjoint files are each more than a small fix, as
   its role file says. At the end it records the last change of the model it took into
   account.
3. **The reviewer**, after an implementer run (its trigger is the
   implementer's report, in words) or on comments about the refactoring
   part. The first time, it writes the whole refactoring part; later, it
   judges again the items the run touched.

Then set `awaiting-docs` (see **Status**) and wait: the page shows « Write
docs » and « Write docs and create PR » at the bottom of the code tab. Once
the doc pass has run, a pass ends on `awaiting-pr` instead, and the page
shows « Create PR » there.

The reviewer's report can name items judged `diverges` or `move`, or
comments that ask for a code change: run the implementer on them, then the
reviewer, in the same pass. An item the reviewer judges `diverges` again
right after the implementer worked on it is not sent back a second time: ask
the user in the page what to do with it.

### The doc pass

The **doc pass** carries the model into the repo's docs, once the code
carries it. The user starts it with « Write docs » (a batch with `action:
write-docs`), or with « Write docs and create PR » (the same action with
`"then_pr": true`), which chains it to closing with no pause. It runs
once, and the page never shows « Write docs » again; after it, the docs
change as **The docs after the doc pass** says.

It has agents of its own, started from the session folder, never the
implementer: the documenter (its role file), then the skill agents (see
**Starting a skill agent**), then the documenter again. Each one runs
after the previous one ends.

1. Run the batch's comments first, as **Implementation** says.
2. **The documenter prepares.** Start it with the trigger `"« Write
   docs »"`, the batch id and every « write repo lexicon » batch that
   waited for the doc pass. It refreshes the doc set on the real diff (a
   README the code moved with its folder listed at its new path, nothing
   left at the old one), writes the lexicons and records the **write
   order**: the lexicons first; then each **central subtree** (a folder
   holding a file the code map ties to a core concept of the model, the
   earlier concept's section first), from its deepest folders up; then the
   other docs, each folder after its subfolders; then the root
   `README.md`; each `CLAUDE.md` and `AGENTS.md` last. Its report lists the
   READMEs of the doc set in that order.
3. **One write-readme agent per README**, one after the other, in the
   write order, so the README of a folder finds those of its subfolders
   written. Each writes the README's parts: a **draft** for a missing
   README, an **edit** otherwise (which retitles a README whose map and
   usage are not under `## Files` and `## Usage` yet), and a **full
   rewrite** of its parts with the `rewrite` argument, which you give when
   a waiting rewrite request names the README. A README whose folder the
   branch removes gets no write-readme agent: there is no code left to
   describe, and the move plan says where its passages go. Give each the
   comments that waited on that README's parts. Give each run report in
   the terminal.
4. **One document-feature agent**, on every README of the doc set, in the
   write order, with the comments that waited for the doc pass on a
   README's folder model. It reads the boundary with write-readme's parts
   by the headings step 3 set, and creates no README. It writes the
   **concept triage**, then, README by README, a **local model edit**
   (each passage stays in the README) or, for a **restructuring**
   (passages must leave it), the **move plan** of its folder model. Give
   its run report in the terminal.

   **The stop on the move plan.** When its report has a line `move plan
   waiting`, it wrote no folder model, those of the READMEs no plan names
   included. The stop holds only what document-feature writes: the
   write-readme agents of step 3 wrote their parts from the code, which
   the plan does not change, and no README is to be put back. Set
   `view-concept status <slug> awaiting-moves`, say in one terminal line
   which READMEs wait (every README of the doc set), and wait, with or
   without `then_pr`: the user reads the move plans in the Doc tab,
   comments on their rows, and sends « Write READMEs » (a batch with
   `action: write-readmes`). Until it comes, hold the comments on the
   plans' rows, the comments on a README's text and the rewrite requests.
   Then start a document-feature agent again, on the same READMEs, with
   « Write READMEs », the comments on the plans' rows and the held
   comments on a README's folder model: it writes the folder model of
   every README of the doc set, those the plans name from the plans and
   the comments, and records the missing facts of each old folder model
   on the README it became. Go on to step 5.
5. **A second write-readme agent**, with `rewrite`, on each README the
   document-feature report marks `role change` (its edit of step 3 no
   longer fits the folder's new reader) and on each README a rewrite
   request held during the stop names, with the comments held on its
   parts. It rewrites the README's parts in full and copies the folder
   model after them. On each other README that has comments held during
   the stop on its parts (write-readme's passages: the top, `## Files`,
   `## Usage`), start a write-readme agent without `rewrite`, an edit,
   with those comments. Give each run report in the terminal.
6. **The documenter finishes.** Start it with the trigger
   `"« finish docs »"`, the reports of the skill agents in words
   (`"write-readme report: <the report>"` per README, in the write order,
   then `"document-feature report: <the report>"`, then the reports of
   step 5), and the comments
   the doc pass handled: those on the text of a doc that is not a README,
   which it applies, and those the skill agents applied, which it
   resolves. It writes the docs that are not READMEs (only the sentences
   the code contradicts corrected; in a `CLAUDE.md` or an `AGENTS.md`,
   only the sentences it adds or changes that pass the **sentence test**:
   without the sentence, an agent would act otherwise), records each
   README's failure indicator and the missing facts write-readme reported,
   makes the doc pass's one commit, and classes the minor docs. Its report
   says « doc pass ». When its `to skill agents:` block has `doc pass
   README <path>` lines (a README a `no README:` line of document-feature
   added to the doc set), run steps 3 to 6 on those READMEs alone before
   step 7, so that neither the reviewer nor a PR opened with `then_pr`
   comes before their doc pass.
7. Start the reviewer with the documenter's report (in words, « doc pass »
   in it): it judges the items the doc pass changed, as for any
   implementer run, then reads every doc of the doc set against the model
   and flags each **stale passage**, a passage the model contradicts, with
   `view-concept stale`. The Doc tab draws a wavy underline on it, with
   the note on hover; the user comments on it, and the passage is
   rewritten or the flag dropped, as **The docs after the doc pass** says.
8. With « Write docs », go on as **Implementation** says (an item judged
   `diverges` or `move` goes back to the implementer), then set
   `awaiting-pr`: the user reads the docs in the Doc tab and comments on
   them, and « Create PR » shows at the bottom of the code tab. With
   `then_pr`, go to **Closing** at once, whatever the verdicts: the PR
   opens with the stale passages flagged, not fixed; the user reads the
   verdicts and the flags after, and a later comment on a doc updates the
   PR.

### The docs after the doc pass

Each event on the docs starts the agents below, in the next pass, the
skill agents first, then the documenter, which commits and resolves. A
passage of a README is **write-readme's** when it sits at the top, before
the first `##` heading, or under `## Files` or `## Usage` (or the headings
the repo's conventions impose for them); any other passage is the folder
model, **document-feature's**.

| Event | Agents |
|---|---|
| a comment on a README's text (`(doc <path>)`) | a write-readme agent on that README, for a passage of its parts, a document-feature agent for a passage of the folder model; then the documenter, with the agent's report and the comment id |
| a rewrite request | a write-readme agent on that README with `rewrite`; then the documenter, with its report |
| a comment on a row of the concept triage (`(triage <id>)`) | a document-feature agent on the READMEs of the doc set, with the comment; then the documenter, with its report |
| a comment on the text of a doc that is not a README, on the doc set list, on a lexicon or on a missing fact; « write repo lexicon » | the documenter |
| the documenter's report lists work `to skill agents:` (a fact to take back, a README clause a lexicon entry copies, a README added to the doc set) | the skill agent each line names, on its README; then the documenter, with its report; a README added to the doc set gets the whole doc pass, steps 3 to 6, on it alone |
| the implementer's report lists `docs made false:` | the doc pass again on those docs: on each README, a write-readme agent then a document-feature agent; then the documenter, with their reports and the implementer's |

While the phase is `awaiting-moves`, a comment on a README's text and a
rewrite request wait for « Write READMEs » (step 4).

## Closing

Closing starts when the user asks for the PR: a batch with
`action: create-pr`, or saying so in the terminal, or the end of a doc pass
started with `then_pr`. Apply the batch's comments first, as
**Implementation** says. Then close in the same turn, without asking again:
the click was the go. Closing writes nothing in the repo: the docs were
written in the doc pass. When the user asks for the PR before the doc pass
has run, run the doc pass first, as **The doc pass** says with `then_pr`.

Write the PR description with `short-pr-description`, using the change
history as its Decisions (`view-concept changes <slug>` prints it as
bullets; keep the changes the user asked for or agreed to, and merge the
ones a later change undid). Push the branch and open the PR with
`gh pr create --body-file <file>`, or, when the branch already has one,
update it with `gh pr edit <n> --body-file <file>`. Record its link with
`view-concept pr <slug> <url>`: the page links it in its top bar and at the
end of the code tab, and « Create PR » becomes « Update PR ». Give the PR
link in the terminal too: the user reviews it in VS Code. No vault export.

Once the PR is open, a later pass ends on `awaiting-pr` too; « Update PR »
(the same `create-pr` action) pushes the new commits and updates the
description.
