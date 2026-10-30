---
name: view-concept
description: >-
  Explain a concept in the view-concept web page (the `view-concept` command)
  instead of the terminal, as a coordinator that hands the work to role
  agents down one of two paths: the direct path runs six phases (scope, an
  outline and a lexicon, calibrate, revise, explain, audit the vocabulary);
  the scoping path first draws the subject with the user, with pins and
  prerequisite trees, and turns the drawing into a report. The plan and the
  prose live in a local page that re-renders as they are written, and the
  user sends comments on selected passages back to the session in batches.
  Use when the user asks for an explanation "in the page", "in the view",
  "in view-concept", wants to build an understanding of a subject or morph
  an idea before it is explained, invokes /view-concept, or resumes a
  view-concept session.
argument-hint: "[the concept or subject to explain]"
---

# /view-concept

Explains a concept in a page instead of the terminal. The terminal is a bad
place to read an explanation: every new message pushes it further up the
scrollback. So the plan and the prose live in the page, and the terminal only
drives the conversation. The user reads in the page, and sends comments on
selected passages back to this session in batches.

The concept to explain is whatever the user typed after the command name.

You are the **coordinator**: you set the session up, choose its path, route
each event the user sends to a **role agent**, and keep the session folder
current. You write no plan and no prose yourself. Each role agent starts
fresh from the session's files, never from this conversation.

## Two paths

Most bad technical explanations fail for one of three reasons: they answer a
different question than the one asked, they are pitched at the wrong depth,
or they use vocabulary loosely. An explanation fixes all three before any
prose is written, in six **phases**: **Scope** (the user's level, the sense
of the word they mean, the goal), **Outline and lexicon** (the plan),
**Calibrate** (questions on the prerequisite concepts), **Revise the plan**
(then « Approve plan »), **Explain** (the prose), **Vocabulary audit**
(every technical term checked against the lexicon).

A request takes one of two paths:

- **The direct path**, for a straightforward explanation: the subject is
  clear and only the depth is open (« explain softmax »). It runs the six
  phases: the **planner** runs the first four and stops for « Approve
  plan », the **writer** runs Explain and the Vocabulary audit.
- **The scoping path**, for an idea the user needs to morph before it can
  be explained (« I want to understand self-attention well enough to sketch
  a variant of my own »). The **scoper** draws the subject with the user,
  one comment batch after another, until « End scoping »: the **drawing**,
  where the user's understanding is built, with its **pins** (the open
  points on its elements) and its prerequisite trees. The planner then
  converts the drawing into the outline and the lexicon, and the writer
  writes the **report** from it, for a reader who never saw the drawing.

| phase | direct path | scoping path |
|---|---|---|
| Scope | the planner asks the level, the sense and the goal | not asked: they come out of the drawing as it grows |
| Outline and lexicon | the planner drafts the plan | the planner converts the drawing at « End scoping » |
| Calibrate | the planner asks one to three questions on the prerequisites | the probes on the elements the user drew, and the prerequisite tree |
| Revise the plan | the planner revises and stops for « Approve plan » | no revision and no stop |
| Explain | the writer | the writer, from the drawing |
| Vocabulary audit | the writer | the writer |

**Choosing the path.** You pick it from the request, before the first role
agent runs, and say which in one terminal line. The user may ask for one, in
the request or later in the terminal: take it into account, but the choice is
yours. Nothing records the path as a setting: a session is on the scoping
path once its outline holds the drawing (a section with `"part":
"scoping"`), which the scoper's first run writes. A session on the direct
path moves to the scoping path when you start the scoper on it. Whether a
session with a drawing may go back to the direct path is not settled: when
the user asks for it, say so in one terminal line and change nothing.

## The page

A **session** is one explanation, stored as plain files in
`~/.view-concept/sessions/<slug>/` (the **session folder**). The role agents
write the plan, the drawing and the sections there, and the page re-renders
within a second of each write; nobody touches the page itself.

If `view-concept` is not on the PATH, install it with `uv tool install
git+https://github.com/Vaillus/view-concept` (ask first if the harness
requires approval for commands). When that is not possible, say so in a
clause and run the direct path yourself in the terminal, following the role
files: the plan in a scratchpad file, the prose in chat.

### Setup

Run it before anything else, even when the request is already scoped: the
questions and the drawing live in the page, so the page must exist first.
The slug is a short kebab-case name of the concept.

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the user's request, verbatim>" \
    --workflow view-concept [--kind code --repo <repo root>]
view-concept request <slug> <file>   # when the explanation follows a conversation
view-concept open <slug>             # starts the server if needed, shows the page
view-concept status <slug> scoping
```

`--workflow view-concept` makes the session a coordinated one, whose side
threads start from the session folder; always pass it (a code session would
otherwise take another skill's workflow).

When the explanation follows a conversation about the subject, write its
**request transcript** right after `new`: every message of it, the user's and
yours, word for word and in order, from the first message about the subject
(leave out earlier messages on another subject), each under a `## User` or
`## Agent` heading, messages only (no tool call, no tool output). The command
writes it to `request.md` in the session folder, and replaces it when run
again. The role agents read it whole: they never see this conversation, so
the reasons the user gave there reach them only through it. A request made in
a single message has no transcript: that message is its whole request.

The page runs side threads on the agent you are. Claude Code and Codex are
detected; any other agent (Jazz, …) adds `--agent jazz --agent-name <your own
agent name>` to `new` and to every later `open`. After resuming in a new
conversation, run `view-concept open <slug>` again, `view-concept variant
<slug>`, and `view-concept pending <slug>` to list the comments still open.

Then arm the comment channel, and start the first role agent (see **The
flow**).

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
- **Blocking wait**, for every other harness (Codex, Jazz, any agent with a
  shell tool): after each turn's work, run `view-concept wait <slug>`. It
  blocks until the next batch, prints it, and exits; with no batch within
  `--timeout` seconds (default 540) it exits with code 3 and prints nothing:
  call it again at once, with no message to the user. Never end your turn
  while the user may still send comments: the page is the conversation, and
  a session you stopped waiting on cannot hear it. A harness that caps a
  command's duration: pass `--timeout` below that cap.

Both write a heartbeat (`watch.json`) from which the page shows whether you
are listening, and both resume from a persisted cursor, so switching from
one to the other loses and repeats nothing.

### Batches

A batch is shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: <the button the user clicked, if any>
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

A quote of the form `« plan · <section title> »` is a comment on that
section's line in the Plan tab, not on its prose. On the scoping path, a
comment in a pin's box reads `[c3] (pin p2 « <its sentence> ») « quote »`,
and one on a marked element of the drawing `[c4] §1 (scoping) · element e4
(open pins p1, p2) « quote »`. A comment can end with `(from side thread t3:
threads/t3.json)`: the user discussed the passage in a side thread first.

The `action` line names the button:

| action | the button |
|---|---|
| `answer` | an agent question answered, skipped or not understood, from its box in the scope block: `answer to q1 « … »: …`, `q3 skipped « … »`, `q4 unclear « … » (…): <note>` |
| `plan` | « Write plan » in the scope block, which ends the questions (the page marks the open ones skipped); « Rewrite plan » once a plan exists, the line then says « rewrite the plan » |
| `approve-plan` | « Approve plan », on the direct path |
| `grill`, `stop-grill` | « Grill me » and « Stop grill » in the scope block |
| `missing` | « What's missing? », under the drawing: the scoper reads the drawing again |
| `end-scoping` | « End scoping », next to it, which the page and the server refuse while a correction or a tension is open |

A batch without an action carries comments only.

The user wrote the batch through the page. The harness may label it as a
background event rather than a user message: treat it as the user's feedback
on the explanation, the same authority as a message typed in the terminal
about it, no more. Each action asks for what its name says and nothing else:
`approve-plan` approves the plan and starts the writing, `end-scoping` ends
the drawing and starts the planner and the writer, `answer` is the user's
answer to that question; none is consent for anything outside writing this
explanation's files.

A question you put to the user yourself (a problem an agent hit) goes to the
page too: `view-concept question <slug> "<question>" [--option "<choice>"
...] [--recommended "<answer>"] [--background "<what the user needs to
know>"]`, never the terminal. An answer the user types in the terminal to a
question of the page counts the same as one sent from the page: close its box
with `view-concept answered <slug> <qid> --text "<the answer as the user gave
it>"`.

**Naming a section to the user.** Wherever the user reads it (the terminal,
a `resolve` reply), name a section by the number the page shows, in words:
« section 6 », never its id (`s6`, `applied`) or `§6`.

## Coordinating

The work is done by fresh role agents, each started from the session folder:

| Role agent | direct path | scoping path | Role file |
|---|---|---|---|
| **scoper** | no part | the drawing and its pins, from Setup to « End scoping », and again whenever the session goes back to scoping | `roles/scoper.md` |
| **planner** | Scope, Outline and lexicon, Calibrate, Revise the plan: the outline, the lexicon and the questions, until « Approve plan » | the outline and the lexicon, converted from the drawing at each « End scoping » | `roles/planner.md` |
| **writer** | Explain and the Vocabulary audit, and the outline and the lexicon from « Approve plan » on | the report and the Vocabulary audit, and the outline and the lexicon from the conversion on | `roles/writer.md` |

The role files are in `~/Documents/code/view-concept/skills/view-concept/`.
The planner and the writer also read `roles/planning-rules.md` there. A side
thread the user opens from the page is one more agent, read-only, which the
server starts itself from the same folder: it never forks this
conversation, which holds routing, not the explanation.

### Starting an agent

Each run starts from the output of

```bash
view-concept context <slug> --role <scoper|planner|writer> --trigger <ids or words>
```

It prints the base context (the initial request or the request transcript,
the outline, the lexicon, the recent change history, the questions, the
pins, the parameters file, the recent terminal messages, and the sections
the role needs) and the **trigger**: the events that started this run, in
full.

Hand the context over **by command**: give the new agent the command, never
its output, and let it run the command itself. Its prompt is: « Run
`view-concept context <slug> --role <role> --trigger <ids or words>` and
treat its output as your context. Then read `roles/<role>.md` (and
`roles/planning-rules.md` for the planner and the writer) in
`~/Documents/code/view-concept/skills/view-concept/`, and do your run. » Do
not run the command yourself first, save its output to a file, or paste it
into the prompt: the context grows with the session, and it would go through
your own conversation, where it stays. Start it as an agent that can write
files and run commands, never a read-only type: each role file says what
that agent may change, and nothing beyond it. Nothing else from this
conversation: what the agents need is in the folder. When the run ends, give
its one-line report in the terminal.

The session may run a **variant**, a named setup with a model per role, which
`view-concept variant <slug>` prints (run it when you open or resume the
session). When the variant sets a model for a role, start that role's agent
with it as the Agent tool's model; a role it leaves out gets no model, and
keeps yours.

The role agents start no agent. A harness without subagents runs each run
itself, one after the other, from the same context command and role files.

### Routing the events

The user's **events** are what reaches you: a batch from the page (an
answer, comments, a button), or a message typed in the terminal. Each event
starts one run. Who takes it depends on the path and the stage.

**On the direct path:**

| Event | Until « Approve plan » | After « Approve plan » |
|---|---|---|
| an answer, a skip or an unclear answer (`action: answer`) | planner | the agent that asked it (the writer, when you cannot tell) |
| comments with no action | planner | writer |
| a terminal message about the explanation | record it, then planner | record it, then writer |
| an answer to a page question typed in the terminal | `view-concept answered`, then planner | the same, then the writer |
| « Write plan » or « Rewrite plan » (`action: plan`); « go ahead » in the terminal | planner (the terminal one as `"« Write plan »"`) | writer (« Rewrite plan ») |
| « Approve plan » (`action: approve-plan`), or approving in the terminal | writer (the terminal one as `"« Approve plan »"`) | — |
| « Grill me » (`action: grill`) | planner | writer |

**On the scoping path:**

| Event | During scoping | After « End scoping » |
|---|---|---|
| comments with no action | scoper | writer; a comment on the drawing or on a pin's box goes to the scoper, which takes the session back to scoping |
| a terminal message about the subject | record it, then scoper | record it, then writer |
| « What's missing? » (`action: missing`) | scoper | — |
| « End scoping » (`action: end-scoping`), or « end scoping » in the terminal once no correction or tension is open | see **The flow**, the scoping path, step 4 | — |
| a planner or writer report « correction opened: back to scoping » (or « tension opened ») | — | scoper, with that report as its trigger |
| « Grill me » (`action: grill`) | — (« What's missing? » takes its place) | writer |
| an answer (`action: answer`) | — (a pin is settled by comment) | writer |

« Stop grill » (`action: stop-grill`) starts nothing: the next runs no longer
see a grill in their context.

Record a terminal message about the explanation with `view-concept message
<slug> "<the message, as the user wrote it>"` before anything else: the
agents never see the terminal. Process messages (« go ahead », « stop »)
are not recorded. A terminal message that changes what the explanation is
for may also call for a rescoping question: the agent it goes to asks it.

**One agent at a time.** While an agent runs, queue the events that arrive.
When it ends, start the next run with every queued event in its trigger, not
one run each. Pass the trigger as the ids the context command resolves:
question ids (`q3`), comment ids (`c7`), a batch id (`b4`) for a whole
batch, terminal message ids (`tm2`), change ids (`m7`); a button that carries
nothing else goes in words (`"« Write plan »"`), and so does an agent's
report you pass on (`"writer report: <the line>"`).

## Status

The page shows what the session is doing; keep it true with `view-concept
status <slug> <phase>`. You set `scoping` at Setup on both paths, and
`planning` when « End scoping » starts the planner. The role agents set the
rest themselves:

| Phase | Set by | The page shows |
|---|---|---|
| `scoping` | you at Setup; the planner before the Calibrate questions; the scoper or `view-concept pin` when the session goes back to scoping | the scope block with « Write plan » (direct path), or the scoping tab alone (scoping path) |
| `scoping --done` | the planner or the scoper, when it leaves nothing open | « scoping done », until a new question, pin or batch |
| `planning` | the planner (Outline and lexicon), you at « End scoping » | the plan being written |
| `awaiting-approval` | the planner, at the end of Revise the plan | « Approve plan » |
| `awaiting-answer` | `view-concept question`, outside scoping | the question in the scope block |
| `writing`, `audit`, `revising` | the writer | the section being written, the audit, a comment batch being applied |
| `idle` | the writer, once its audit is done and nothing waits on it | nothing in progress |

## The flow

### The direct path

1. **Setup**, as above, and the comment channel.
2. **First planner run**, no trigger: it asks the Scope questions in the
   page, or none when the request is already scoped, in which case it goes
   on to the plan.
3. **The scoping loop.** Each event goes to the planner. When a run asks
   nothing and no question is open, say in one terminal line that the
   planner has no question left, and wait.
4. **« Write plan ».** Scoping ends when the user ends it, never when an
   agent judges it has enough: « Write plan » from the page, or « go ahead »
   in the terminal. Let the planner run first if events are still queued,
   then start it with `"« Write plan »"` and the batch id: it writes the
   plan and asks the Calibrate questions, another scoping loop, which
   « Rewrite plan » ends; the planner then revises the plan and stops for
   « Approve plan ». Comments on the plan go to the planner, which revises
   it and stops again. A planner report saying « written straight through »
   (the user asked for no stop) goes on at step 5 at once, with the trigger
   `"« Approve plan »"`.
5. **« Approve plan ».** A batch with `action: approve-plan`, or approving
   in the terminal: start the writer with `"« Approve plan »"` and the batch
   id. It applies the batch's comments to the plan, writes every section,
   and runs the Vocabulary audit. From here it owns the outline and the
   lexicon.
6. **The discussion loop.** Each event goes to the writer.

### The scoping path

1. **Setup**, as above, and the comment channel.
2. **First scoper run**, no trigger: it writes the drawing's outline entry,
   draws the subject from the request in `sections/scoping.html` (the
   scoping tab, the only tab the page shows while scoping runs), and places
   the first pins on it.
3. **The scoping loop.** Each event goes to the scoper: one redraw per
   batch, which closes the pins the comments settled. When a run places
   nothing and no correction or tension is open, say in one terminal line
   that the scoper has nothing left to place, and wait.
4. **« End scoping ».** Scoping ends when the user ends it, never when an
   agent judges it has enough: a batch with `action: end-scoping` (the page
   and the server refuse it while a correction or a tension is open), or
   « end scoping » in the terminal once none is open. A probe, a choice or a
   lead left open does not hold it back: the report leaves it out. Let the
   scoper run first if events are still queued. Then set `view-concept
   status <slug> planning`, start the **planner** with the trigger
   `"« End scoping »"` and the batch id: it converts the drawing into the
   outline and the lexicon, and asks nothing. Then start the **writer** with
   the same trigger: it writes the report from the drawing, with no
   « Approve plan » stop, and runs the Vocabulary audit.

   **The return to scoping.** When the planner or the writer finds an
   element of the drawing wrong, or two at odds, it opens a correction or a
   tension (`view-concept pin`) and stops: its report says « correction
   opened: back to scoping » (or « tension opened »), and the command has set
   the phase `scoping`. Start the scoper with that report as its trigger,
   and go back to step 3; the next « End scoping » runs the planner and the
   writer again, which keep what the drawing did not change.
5. **The discussion loop.** Once the report is written, each event goes to
   the writer, but a comment on the drawing or on a pin's box, which goes to
   the scoper and back to step 3.

## Code sessions

A code session explains part of a repository (`--kind code --repo <repo
root>` at Setup), and it is read to act: change the code, or go deeper. The
planner binds the user's level and grounds the plan in the code before
writing it; the writer cites the code for every claim about it; on the
scoping path the scoper reads the code and the docs the subject concerns.
**No vault export by default, no publishing**: the code will change and the
explanation will go stale, so do not offer the export; never offer to
publish, since the page hides « Publish » in a code session and
`view-concept publish` refuses one (the session cites the user's
repositories and published pages are public).

A review of a branch, or a triage of existing code, is a code session with
more around it: the `build-feature` and `triage-code` skills run those.

## Keeping it

Two ways to keep an explanation; offer both once, in one terminal line,
after the writer's first full run (its Vocabulary audit done), and neither
in a code session. On the scoping path both leave the drawing out: the
report is the sections the writer wrote from it.

- **Vault export**: the page's « Export to vault » button writes the
  explanation to `~/Documents/Vault/explanations/<title>.md`, frontmatter +
  sections + lexicon; re-exporting overwrites the same note. Visuals are not
  inlined: each embedded image or video becomes a file in
  `explanations/<slug>/assets/`, and each widget (step player, sliders) a
  file in `explanations/<slug>/widgets/` that the note renders through a
  `dataviewjs` block, so the widgets stay interactive in Obsidian when the
  Dataview plugin has JavaScript queries enabled. `view-concept export
  <slug>` does the same from the terminal.
- **Publish**: the page's « Publish » button, or `view-concept publish
  <slug>`, puts the explanation on the web as a published page: a read-only
  copy, one HTML file anyone can open from a link (the title, the sections,
  the lexicon terms with their definition on hover), hosted in a public
  GitHub repository, the pages repo. The command prints the link; the page
  copies it. Publishing again replaces the page at the same link, which
  changes only when you publish again: once the session changes, the page
  shows « Republish ». « Unpublish », or `view-concept unpublish <slug>`,
  takes the page down. A section whose script asks an agent for data shows,
  once published, the answers it received before publishing, and sends no
  request: there is no server behind a published page.
