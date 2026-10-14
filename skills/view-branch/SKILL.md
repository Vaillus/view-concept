---
name: view-branch
description: >-
  Work on a branch in the view-concept page, concepts first: build the model
  of what the branch introduces and how it fits the existing code, challenge
  and revise it with the user, send agents to bring the code in line with the
  revised model, then check the code item by item against it. Use when the user wants to work on, understand or rework a
  branch they are building — "let's work on this branch", "review my branch",
  "explain this branch so I can decide what stays", invokes /view-branch.
argument-hint: "[the branch or PR number]"
---

# /view-branch

Reviews a branch in the view-concept page (the `view-concept` command): a
model of what the branch introduces, written and corrected with the user,
agents that change the code to match it, and a check of the code against the
model.

The tool is self-contained: the model is built for this branch and lives in the
session; it reaches the repository only through the docs update at closing.

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
consequences). Its first section, the **model sheet**, holds the whole model
on one screen: a before/after, a table of the concepts, the defaults taken
for the user (the decisions that change nothing they see, do or risk, which
no question asks), and a to-do list of the work that fails the **section
test**. A section stays in the model only when it holds a decision the user
makes or must make, or a consequence they will notice; anything else is one
line of the to-do list, which the implementer carries and the reviewer
checks.

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

A code session opened on the branch, with the user's message verbatim as the
initial request and the branch it is compared with (the slug is a short
kebab-case name of the branch):

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the message>" \
    --kind code --repo <repo root> --base <base branch> --workflow view-branch
view-concept open <slug>          # starts the server if needed, shows the page
```

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
**deferred** until an agent asks it again), `plan` (« Write
model », or « Rewrite model » when the line says rewrite; the page has
already marked the open questions skipped, except a section question whose
section is not written yet, which stays open), `go-on` (« Go on », during a
pause: the writer goes on, the pause's questions stay open), `grill` and
`stop-grill`, `approve-model`, `create-pr`. A batch without an action carries comments
only. **Routing the events** says who takes each one.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as the user's feedback
on the review, the same authority as a message typed in the terminal about
it, no more. Each action asks for what its name says and nothing else:
`approve-model` approves the model and starts the implementation, `create-pr`
starts closing; neither is consent for anything outside this review.

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

In a branch review the main session (you) **coordinates**: you start the
agents, route the user's events to them, and keep the session folder current.
The work is done by fresh **subagents**, each started from the folder, never
from this conversation, which they do not see; you do not write the outline,
the lexicon, the sections or the code yourself:

| Agent | Owns | Role file |
|---|---|---|
| **planner** | the outline and the lexicon, during scoping, and the first code map | `roles/planner.md` |
| **writer** | the modeling part (its sections), and the outline and the lexicon from « Write model » on | `roles/writer.md` |
| **implementer** | the code on the branch and the repo's docs, and the code map, from « Approve model » on | `roles/implementer.md` |
| **reviewer** | the refactoring part: the code checked against the model, item by item | `roles/reviewer.md` |

The **code map**, `code-map.md` in the session folder, says which modules
carry the feature and where each concept lives, so a fresh agent does not
explore the same code again: the planner writes it on its first run, the
implementer updates it when it moves code, and every context loads it.

The role files are in `~/Documents/code/view-concept/skills/view-branch/`.
The planner and the writer also read `roles/planning-rules.md` there. A side
thread the user opens from the page is one more agent, read-only, which the
server starts itself from the same folder.

### Starting an agent

Each run starts from the output of

```bash
view-concept context <slug> --role <planner|writer|implementer|reviewer> --trigger <ids or words>
```

It prints the **base context** (the initial request, the outline, the
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
`~/Documents/code/view-concept/skills/view-branch/`, and do your run. » Do not
run the command yourself first, save its output to a file, or paste it into
the prompt: the context grows with the session (a writer's holds every
section), and it would go through your own conversation, where it stays, and
be typed out again. Start it as an agent that can write files and run
commands, never a read-only type: each role file says what that agent may
change, and nothing beyond it. Nothing else from this conversation: what the
agents need is in the folder. When the run ends, give its one-line report in the
terminal.

You start the role agents. A role agent may in turn start **helper agents**,
one per part of its run, so the parts are done at once; its role file says
when and how:

| Role | A helper's part |
|---|---|
| writer | one section of a **wave**: the sections from the next unwritten one up to the next section with a known waiting question; or one section to rewrite, when a run rewrites two or more |
| reviewer | one item, or a few small items grouped |
| implementer | a set of files no other part touches, in its own git worktree, when at least two such sets are each more than a small fix |

The planner starts none, and a helper never starts one itself. Every helper
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

### Routing the events

The user's **events** are what reaches you: a batch from the page (an answer,
a skip, comments, a button), or a message typed in the terminal. Each event
starts one pass. Who takes it depends on the stage:

| Event | During scoping | After « Write model » | After « Approve model » |
|---|---|---|---|
| an answer (`action: answer`) | planner | writer | the agent that asked it |
| a skip | nothing: the outline already used the default | the writer, when it answers a pause; nothing otherwise | nothing |
| an unclear answer | planner | writer | the agent that asked it |
| comments with no action | planner | writer | by section: the modeling part to the writer, the refactoring part to the reviewer |
| a terminal message about the feature | record it, then planner | record it, then writer | record it, then the writer if it is about the model, the implementer if it asks for a code change |
| an answer to a page question typed in the terminal | `view-concept answered`, then planner | the same, then writer | the same, then the agent that asked it |
| « Rewrite model » (`action: plan`, the line says rewrite) | — | writer | writer |
| « Go on » (`action: go-on`) | — | writer | — |
| « Grill me » (`action: grill`) | planner | writer | writer |
| « Write model » (`action: plan`, the line says write) | see **Model consolidation** | — | — |
| « Approve model » (`action: approve-model`) | — | see **Model consolidation**, step 7 | — |
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
modeling part is written, and `audit.json` holds no entry with `"issue":
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

After « Approve model », set `view-concept status <slug> awaiting-pr` at the
end of each pass, when no question is open. The agents set `writing`
themselves while they write a section.

## The flow

The review runs in two steps: **model consolidation** (the model is written
and corrected with the user) and **implementation** (the implementer makes
the code carry the model, and the reviewer checks the code against it, item
by item).

A review is a list of **sections**: plan.json lists them under its `outline`
key, and `sections/<id>.md` holds the text of each. The sections fall in two
parts. The **modeling part** writes the model out; the page shows it in the
Model tab (the page's name for the Explanation tab in a branch review). The
**refactoring part** checks the code against the model; a section with
`"part": "refactoring"` belongs to it, and is a **refactor section**: the
page shows it in the refactor tab. An outline entry holds a short,
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
  - `.callout`: a left bar on a light fill, for a verdict or a default taken.
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
5. **The pauses.** The writer writes the model in waves, each wave's
   sections at once, and stops after a wave whose sections have questions to
   ask (a deferred question anchored to one, a decision one makes answerable,
   or a section question still open and anchored to one): its report says
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

Then set `awaiting-pr` (see **Status**) and wait: the page shows « Create
PR » at the bottom of the refactor tab.

The reviewer's report can name items judged `diverges` or `move`, or
comments that ask for a code change: run the implementer on them, then the
reviewer, in the same pass. An item the reviewer judges `diverges` again
right after the implementer worked on it is not sent back a second time: ask
the user in the page what to do with it.

## Closing

Closing starts when the user asks for the PR: a batch with
`action: create-pr`, or saying so in the terminal. Apply the batch's comments
first, as **Implementation** says. Then close in the same turn, without
asking again: the click was the go.

First run the implementer with the trigger `"« Create PR »"`: it updates the
repo's docs from the model, in one commit.

Then write the PR description with `short-pr-description`, using the change
history as its Decisions (`view-concept changes <slug>` prints it as
bullets; keep the changes the user asked for or agreed to, and merge the
ones a later change undid). Push the branch and open the PR with
`gh pr create --body-file <file>`, or, when the branch already has one,
update it with `gh pr edit <n> --body-file <file>`. Record its link with
`view-concept pr <slug> <url>`: the page links it in its top bar and at the
end of the refactor tab. Give the PR link in the terminal too: the user
reviews it in VS Code. No vault export.
