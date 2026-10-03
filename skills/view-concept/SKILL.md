---
name: view-concept
description: >-
  Run the explain-concept workflow in the view-concept web page (the `view-concept` command) instead of the
  terminal: the plan and the prose live in a local page that re-renders as
  they are written, and the user sends comments on selected passages back to
  the session in batches. Uses explain-concept for the explanation itself and
  owns only the page around it. Use when the
  user asks for an explanation "in the page", "in the view", "in view-concept",
  invokes /view-concept, or resumes a view-concept session.
argument-hint: "[the concept to explain]"
---

# /view-concept

Runs the **`explain-concept`** workflow and puts it in a page. Read and follow
the **`explain-concept`** skill for the explanation itself: its phases,
checkpoints and audit run as written. This skill owns what explain-concept
does not know about: the view-concept page, where each phase's output goes in
it, and how the user's comments come back from it.

This skill is a **user** of explain-concept, not a child: it is not bound by
explain-concept's Specialization contract, and explain-concept does not list
it. Other skills can use this one the same way (`view-branch` is meant to).

The concept to explain is whatever the user typed after the command name.

The terminal is a bad place to read an explanation: every new message pushes it further up the scrollback. So the plan and the prose live in the page, and the terminal only drives the conversation. The user reads in the page, and sends comments on selected passages back to this session in batches.

A **session** is one explanation, stored as plain files in a directory. You write the plan and the sections; the page re-renders within a second of each write; you never touch the page itself.

If `view-concept` is not on the PATH, install it with `uv tool install git+https://github.com/Vaillus/view-concept` (ask first if the harness requires approval for commands); when that is not possible, say so in a clause and follow explain-concept unchanged (scratchpad `explain-plan.md`, prose in chat).

## Where each phase's output goes

| explain-concept phase | In the workspace |
|---|---|
| Start of Phase 1 | run **Setup** below, before any question |
| Phase 1: « Ask one or two questions (with your structured-question tool if the harness has one, else as a plain message) » | ask them in the page with `view-concept question`, never with the terminal question tool, and ask every question you judge relevant rather than one or two (see **Scoping in the page**). Phase 1 ends at the end of scoping, not when your turn ends |
| Phase 1: « If the request is already unambiguous, scoped, and bounded, skip to Phase 2 » | still holds: ask nothing and go to Phase 2. Setup has run first, so the session is open either way |
| Phase 3: the prerequisite questions, then « stop and let the user answer » | ask them in the page too, the same way as the Phase 1 questions (see **Scoping in the page**) |
| Phase 2: « write both artifacts to `explain-plan.md` and surface it with `SendUserFile` » | write them to `plan.json` instead; surface no file. The one-line summary in the message still applies |
| Phase 4: rewrite the plan in place | rewrite `plan.json`; put the one- or two-sentence statement of the revision in `revision` (the page shows it above the outline) |
| Phase 4: « begin Phase 5 only after the user has replied » | a reply is either a terminal message or « Approve plan » in the page (`action: approve-plan`, see **Comment batches**). Anything the user says about the plan, in either place, binds it |
| Phase 5: the prose | each section to `sections/<id>.md`, in outline order, so the page fills in as you go. In the terminal, one line saying the explanation is written, never the prose itself. Later edits rewrite only the sections they touch |
| Phase 5: visuals | a Mermaid block (the page renders it), never a harness widget |
| Phase 6: the list of candidates | first run `view-concept check <slug>`: it writes every forward reference and early use to `audit.json` (issues `forward` and `early`). Then add your own candidates to `audit.json` (the page underlines each term in place), and give the count plus a one-line list in the terminal. The user answers in either place. Fix a forward reference or an early use by the precedence rule: reorder the outline or say it in plain words |

## Setup — once, at the start of Phase 1

Run it before the first question, even when the request is already scoped: the scoping questions are asked in the page, so the page must exist first. The slug is a short kebab-case name of the concept.

```bash
view-concept new "<title>" --slug <slug> --question "<the user's request, verbatim>" \
    [--kind code --repo <repo root>]
view-concept open <slug>          # starts the server if needed, opens the browser
```

The page runs side threads on the agent you are. Claude Code and Codex are detected; any other agent (Jazz, …) adds `--agent jazz --agent-name <your own agent name>` to `new` and to every later `open`.

Use `--kind code` when the explanation is a support for understanding *this* repository — usually on the way to changing it or discussing it further (see **Code sessions** below).

Then arm the comment channel (next section), and start scoping (see **Scoping in the page**).

## The comment channel

The user's comments reach you as **batches**, written by the page to the session's inbox file. Two commands read it; use the first your harness supports, and stay on it for the whole session.

**Background stream** — for a harness with a background-monitor tool (Claude Code's `Monitor`): run `view-concept watch <slug>` under it (`timeout_ms: 1800000`, description `view-concept comments for <slug>`). Each printed batch arrives as an event. A monitor expires after 30 minutes: when its expiry notice arrives, arm it again with the same command and write nothing in the terminal. Always re-arm, however long the silence. Nothing is lost in between: `watch` resumes where it stopped.

**Blocking wait** — for every other harness (Codex, Jazz, any agent with a shell tool): after each turn's work, run `view-concept wait <slug>`. It blocks until the next batch, prints it, and exits; with no batch within `--timeout` seconds (default 540) it exits with code 3 and prints nothing. Handle the batch, then call `wait` again. On exit code 3, call it again at once with no message to the user. Never end your turn while the user may still send comments: the page is the conversation, and a session you stopped waiting on cannot hear it. A harness that caps a command's duration: pass `--timeout` below that cap.

Both commands write a heartbeat (`watch.json`) from which the page shows whether you are listening, and both resume from a persisted cursor, so switching from one to the other loses and repeats nothing. The terminal does not need to report either.

## Files you write

In the directory printed by `new` (`~/.view-concept/sessions/<slug>/`):

| File | Content | Written in |
|---|---|---|
| `plan.json` | `{"title", "question", "created", "revision", "outline": [{"id": "s1", "title", "earns"}], "lexicon": [{"term", "section": "s1", "definition", "tip"}]}` — keep the fields `new` wrote | Phase 2, rewritten in Phase 4; `tip` in Phase 5 |
| `sections/<id>.md` | the prose of one outline section, Markdown, no heading of its own (the page renders the title). `$…$` / `$$…$$` for maths, ```` ```mermaid ```` for diagrams | Phase 5, and every later edit |
| `audit.json` | `[{"term", "section", "issue": "undefined\|metaphor\|ambiguous\|assumes-context\|forward\|early", "note"}]` | Phase 6 |

**The lexicon texts.** The page shows a term's `tip` when the reader hovers any use of it, so it is read mid-sentence, far from the section that introduced the term. Without a `tip`, the page falls back to `definition`, the one-line meaning the plan commits to before the prose. Write both for the **first-use reader**: someone who has read the sections in order up to the term's home section (the section the entry names in `section`) and nothing after. A text that works for this reader works for anyone who has read further; the reverse fails.

**The precedence rule.** Every text about a term (its introducing prose, its `definition`, its `tip`) uses only terms whose home section is at or before that term's home section. When it needs a later term, reorder the outline or say the idea in plain words; never point ahead (« see section 7 »). A term spelled like a common word counts as used wherever the word appears. Two breaches have names: a **forward reference** (a `definition` or `tip` uses a term whose home section comes later) and an **early use** (a term appears in the prose of a section placed before its home section).

**The hover text (`tip`).** Three hard constraints, which bind `definition` too:

1. It obeys the precedence rule.
2. No location details: nothing that says where the thing lives or came from (a file, a key, a script, a section number, a former name) instead of what it is. Those go in the home section's prose, as citations in a code session.
3. It does not repeat what other lexicon entries define. A term that groups other terms with the same home section names the group and what it is for, not each member.

Beyond these, say plainly and briefly what the thing is, as a reader meeting it for the first time needs it; choose the form that serves the term. Markdown and `$…$` are allowed. The `tip` must agree with `definition` and with what the home section says. Write each term's `tip` in Phase 5, when you write the section that introduces the term.

Section ids are stable: when Phase 4 reorders the outline, keep each section's id and change its position. The page anchors the user's comments to ids.

**Naming a section to the user.** Ids are for the files, never for the user. Wherever the user reads it (terminal messages, `resolve` replies, the prose of the sections, the plan), name a section by the number the page shows, in words: « section 6 ». Never write its id (`s6`, `applied`) or a shorthand such as `§6`, even when a batch event uses them.

## Status

The page shows what you are doing; keep it true with `view-concept status <slug> <phase>`, one call per transition:

| When | Command |
|---|---|
| Scoping starts: right after Setup, and again before the Phase 3 questions (see **Scoping in the page**) | `status <slug> scoping` — while it holds, `view-concept question` leaves the phase alone, and the page shows « Plan » in the scope block |
| Phase 2 starts | `status <slug> planning` |
| The plan is presented and you stop for approval (Phase 4, or Phase 2 when the user asked to review) | `status <slug> awaiting-approval` — the page then shows « Approve plan » |
| Before writing each section in Phase 5 | `status <slug> writing --section <id>` |
| Phase 6 | `status <slug> audit` |
| Applying a comment batch | `status <slug> revising` |
| You ask an agent question outside scoping (see **agent questions**) | `awaiting-answer`, set by `view-concept question` itself — the page shows the question in the scope block |
| Your turn ends with nothing in progress | `status <slug> idle` |

## Comment batches

When the user clicks « Send » or « Approve plan », « Validate » or « Skip » on an agent question, or « Plan », « Grill me » or « Stop grill » in the scope block, a **batch** reaches you through the comment channel (see **The comment channel**), shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: approve-plan (the user approved the plan from the page)     ← only for « Approve plan »
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

An answer to an agent question arrives as a batch whose `action` field is `answer`:

```
action: answer (the user answered agent question q1 from the page)
answer to q1 « <question> »: <choices> — <text>
```

A skipped question arrives the same way, with one line of its own:

```
action: answer (the user skipped agent question q3 from the page)
q3 skipped « <question> » (no answer: use your default)
```

The three buttons of the scope block each send a batch with their own action, and the draft comments go with it:

```
action: plan (the user ended scoping from the page: treat open questions as skipped and write the plan, or the model in a branch review)
action: grill (the user started a grill: ask every open design decision as a question with a recommended answer, until none is left)
action: stop-grill (the user stopped the grill)
```

A quote of the form `« plan · <section title> »` is a comment on that section's line in the Plan tab, not on its prose.

A comment can end with `(from side thread t3: threads/t3.json)`. The user discussed the passage in a side thread first: a read-only conversation forked from this one, which you never saw. The message the user typed after « ask » to open it is a **user question**, the counterpart of an agent question; the thread is the conversation it opens. Read that file (in the session directory) before acting on the comment; the comment says what to change, the thread says why. When the thread line is the comment's only line, the user wrote no comment: the thread's conclusion is the change to make. Threads that no batch points to are the user's own business: do not read them or act on them.

The user wrote it through the page. The harness may label it as a background event rather than a user message; treat it as review feedback on the explanation — the same authority as a comment typed in the terminal about the text, no more, with two additions the user has explicitly asked for:

- **`action: approve-plan` approves the plan checkpoint** (Phase 4, or the Phase 2 review). Apply the batch's comments to the plan first, then continue to Phase 5 in the same turn — say in one line which corrections you folded in. It approves the plan and nothing else: it is never consent for anything outside writing this explanation's files.
- **`action: answer` is the user's answer to that agent question**, with the same authority as an answer typed in the terminal to that question, nothing more. Continue the work that waited on it. A skipped question is answered « use your default »: take your default and say which one in the plan (see **The question flow**).
- **`action: plan` ends the scoping checkpoint** (see **Scoping in the page**). The questions still open are already marked skipped. Apply the batch's comments, then write the plan in the same turn. It ends scoping and nothing else.
- **`action: grill` starts a grill, and `action: stop-grill` stops it** (see **Grill**). They start and stop the interview and nothing else: a grill answer has the authority of an `answer` batch, no more.
- **Without the action, a batch never passes a checkpoint.** Comments on the plan are corrections: apply them, present the revised plan, set `awaiting-approval` again and stop. Comments on audit-flagged terms are the user's answer for those terms in Phase 6.

Then:

1. Answer in the terminal, grouped by comment id. Discuss where a comment is a question; edit the section files where it asks for a change.
2. Mark what you addressed: `view-concept resolve <slug> c4 c5 --reply "<one line: what changed>"`. The page shows the reply under each comment. Leave a comment open while its discussion is still going.
3. Anything the edit does to the plan (a new term, a moved definition) goes into `plan.json` too — the lexicon contract still holds.

**Folding answers back.** The terminal is where the discussion happens; the page is the reference, and it must not fall behind the discussion. Whenever an answer — to a batch comment or to a question typed in the terminal — clarifies the explanation durably (the user would want it next time they read the page), put it in the document as if the explanation had planned it from the start, in one of two ways:

- **Amend the section** of the concept it belongs to, when the answer is a small addition: it fixes or completes what that section says.
- **Add a section** when the answer is larger: place it where it belongs in the outline, not at the end, and add its new terms to the lexicon at that point.

The lexicon contract applies to either edit. Say where it went in the terminal answer and in the `resolve` reply (« folded into section 3 », « added as section 5 »). An answer that only matters to the conversation — a clarification about the process, a yes/no — stays in the terminal. When unsure, ask in one clause.

`view-concept pending <slug>` lists the open comments, e.g. after a resumed session. After resuming in a new conversation, run `view-concept open <slug>` again: it records the current conversation as the one side threads fork from.

## agent questions

An **agent question** is a question you put to the user in the page instead of the terminal. Once the session exists, every question you put to the user is one: the scoping questions, a question arising from a batch sent from the page, a model change or a change of scope, a problem an agent hit that needs the user's decision, and the questions of a grill. A question about something the user typed in the terminal stays in the terminal. Ask only while you are listening on the comment channel (a watch armed, or `wait` called right after): the answer comes back through it.

```bash
view-concept question <slug> "<question>" [--option "<choice>" --option "<choice>"] [--multi] [--recommended "<answer>"]
```

`--option` gives the choices (`--multi` lets the user pick several); the page always adds a free-text field. `--recommended` gives the **recommended answer**, the one you would pick: an option, which the page preselects, or a text, which it pre-fills; either is marked « suggested », and validating it unchanged accepts it. Give one whenever you have a suggestion. The command writes `questions.json`; outside the phase `scoping` it also sets the phase `awaiting-answer`. Do not ask the question in the terminal as well; one line saying questions are waiting in the page is enough.

The page shows each open question as a box in the **scope block**, at the top of the Plan tab, oldest first; the answered and skipped ones fold under the open ones, so the plan always shows the scope it was written from. The review pane only shows a line « N questions waiting », which opens the Plan tab. A box has three exits: « Validate » sends the answer, « Skip » sends « no answer, use your default », and a box the user leaves alone stays open. Validating and skipping each send a batch with `action: answer` at once (see **Comment batches**).

### The question flow

The **question flow** is how questions and answers move between you and the user: each validated or skipped box reaches you as its own batch, and you may ask new questions at any time, while others are still open. Its rules:

- **Ask every question you judge relevant.** The user prefers more questions they can ignore to fewer. Ask the **frontier** first: the questions whose answer depends on no other open question. A question that depends on an open one waits until that one is answered or skipped.
- **Add questions as answers arrive.** An answer can open new questions; ask them when it does.
- **Never wait on a question** to continue the work that does not depend on it. The user will leave many questions unanswered, and that is expected: an open box is not a debt.
- **A skipped question** (`q3 skipped « … » (no answer: use your default)`) means: use your default. Say in the plan which default you took (in `revision`, the line the page shows above the outline).
- An answer typed in the terminal counts the same as one sent from the page. Close its box at once with `view-concept answered <slug> <qid> --text "<the answer as the user gave it>"`: the box moves to « answered » marked « (in the terminal) », and no batch comes back, since you already have the answer. The phase is not changed: set the next one yourself.

### Scoping in the page

**Scoping** is the questions asked before the plan is written: Phase 1 (level, sense, goal) and Phase 3 (the prerequisites). Both run in the page, through the question flow:

1. Set `view-concept status <slug> scoping` (Setup has already opened the page). While the phase is `scoping`, asking a question leaves the phase alone, and the page opens the Plan tab and shows « Plan » in the scope block.
2. Ask the questions with `view-concept question`, with `--recommended` when you have a suggestion, never with the harness's terminal question tool. explain-concept's rules on what to ask still hold (level first, in the user's experience; no sense question at the lowest level; nothing the user already said), but not its limit of one or two questions. Then end your turn, listening.
3. Handle each answer batch as it arrives: ask the questions it opens.

**End of scoping.** Scoping ends when the user ends it, never when you judge you have enough: a batch with `action: plan` (« Plan » in the scope block), or « go ahead » in the terminal. Treat every question still open as skipped (after « Plan », the page has already marked them so), and write the plan in the same turn: Phase 2 after the Phase 1 questions (then Phase 3, as explain-concept says), Phase 4 after the Phase 3 questions. When every question is answered and you have none left to ask, say so in one terminal line and wait for the user to end scoping.

A request already fully scoped skips the questions, as explain-concept says: go straight to Phase 2, with no `scoping` phase. The session is open either way.

### Rescoping questions

A **rescoping question** is an agent question asked once the plan exists, because something moved what the session covers: a comment batch, a model change, a terminal message (« actually I want this for debugging »). Ask it with `view-concept question` like any other; it lands in the same scope block. Outside the phase `scoping` it sets `awaiting-answer`, but the question flow still holds: continue the work that does not depend on it. Fold the answer back into the plan (see **Folding answers back**).

### Grill

A **grill** is an optional interview the user starts from the scope block: « Grill me » sends a batch with `action: grill`, and « Stop grill », in the same place while the grill runs, sends `action: stop-grill`. Its topic is what the session is about: the plan here, the model in a branch review.

Work the topic as a **design tree**: the decisions it leaves open, each with the decisions that depend on it (a decision depends on another when you cannot ask it without guessing the other's answer). Then, through the question flow:

1. Ask every decision of the frontier (those whose prerequisites are settled) as an agent question with `--recommended`.
2. Find facts yourself. A question the code, the session files or a command can answer is not a question for the user: look it up, and put only decisions to the user.
3. Each answer settles a decision. Fold it back into the plan (see **Folding answers back**), and ask the decisions it unblocks. A skipped decision takes your recommended answer.
4. The grill ends when no decision is left (say so in one terminal line) or when `action: stop-grill` arrives.

This is the method of the `grilling` skill, when it is installed; this section is all you need to run it.

## Code sessions

A code session explains part of the repository at `--repo`, and it is read to act: change the code, or go deeper with you. The session pre-answers two scoping questions and adds three rules:

- **Level** is bound — the user knows their own code; skip the level question. Still ask **Goal** when it is open (understand before changing, choose between designs, debug).
- **Before Phase 2, ground it**: read the code the explanation covers — the files, the callers, the tests — before outlining. The outline follows how the code actually works, not how its names suggest it works.
- **Citations are required.** Every claim about the code cites where it is true, as inline code: `` `src/pkg/store.py:118` `` (path relative to the repo root, `:line` or `:start-end`). The page turns each citation into a link that opens the file at that line in VS Code. A claim you cannot cite is a claim you have not checked: check it or cut it.
- **No vault export by default.** The code will change and the explanation will go stale, so do not offer the export.

A review of a branch is a code session with more around it: use `view-branch`, which records the model changes (`view-concept change`).

## Keeping it

The page's « Export to vault » button writes the explanation to `~/Documents/Vault/explanations/<title>.md`, frontmatter + sections + lexicon; re-exporting overwrites the same note. `view-concept export <slug>` does the same from the terminal — offer it once the audit is done, except in a code session.
