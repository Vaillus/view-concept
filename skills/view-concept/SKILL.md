---
name: view-concept
description: >-
  Explain a concept in the view-concept web page (the `view-concept` command)
  instead of the terminal, in six phases: scope the request, fix an outline
  and a lexicon, calibrate, revise, explain, audit the vocabulary. The plan
  and the prose live in a local page that re-renders as they are written, and
  the user sends comments on selected passages back to the session in
  batches. Use when the
  user asks for an explanation "in the page", "in the view", "in view-concept",
  invokes /view-concept, or resumes a view-concept session.
argument-hint: "[the concept to explain]"
---

# /view-concept

Explains a concept in a page instead of the terminal. The explanation runs in
six phases, below; this skill also owns the page around them: where each
phase's output goes in it, and how the user's comments come back from it.

The concept to explain is whatever the user typed after the command name.

The terminal is a bad place to read an explanation: every new message pushes it further up the scrollback. So the plan and the prose live in the page, and the terminal only drives the conversation. The user reads in the page, and sends comments on selected passages back to this session in batches.

A **session** is one explanation, stored as plain files in a directory. You write the plan and the sections; the page re-renders within a second of each write; you never touch the page itself.

If `view-concept` is not on the PATH, install it with `uv tool install git+https://github.com/Vaillus/view-concept` (ask first if the harness requires approval for commands); when that is not possible, say so in a clause and run the phases in the terminal: the plan in a scratchpad file, the prose in chat.

## The phases

Most bad technical explanations fail for one of three reasons: they answer a different question than the one asked, they are pitched at the wrong depth, or they use vocabulary loosely. The phases front-load the fixes for all three before any prose is written. Run them in order, and do not run ahead of the user. Announce a transition in a clause, never a paragraph: the phases are scaffolding, the concept is the subject.

### Phase 1 — Scope

Run **Setup** first, then explain nothing yet: work out what is genuinely underdetermined about the request, and ask it in the page (see **Scoping in the page**).

- **Level. Ask it first, always.** Phrase the options in the user's *experience*, never in the topic's vocabulary: « never come across it » / « heard the words, couldn't define them » / « can use it, want the underlying model » / « know it, want it sharper ». An option that needs the explanation to be understood is a broken question: someone who knows nothing about the topic must still be able to tell which option describes them.
- **Sense.** The same word often names things at different layers of a system. Where the user has some familiarity, ask which sense is meant, with an escape option (« not sure, cover how they relate ») when the senses are connected rather than homonyms. At the lowest level, ask no sense question: there is one sense worth giving, and the user has no basis to choose.
- **Goal.** What the explanation is for: a conceptual understanding, a debugging session, a design decision. Usually worth asking even at a low level, in plain words.

Ask only what is open: nothing the user already said. A question whose answer would not change what you write is not worth asking.

**Confusion or deferral is data.** An answer such as « I don't understand the options », « I don't know » or « you decide » points to the lowest level and the narrowest scope; it is not a licence to choose freely. Do not fill the gap with what you know about the user from elsewhere: what they just told you about this topic outranks it. State the reading you took in a clause (« taking this from scratch ») so they can correct it.

When the request is already unambiguous, scoped and bounded, ask nothing and go to Phase 2, saying so in a clause.

### Phase 2 — Outline and lexicon

Fix the vocabulary before writing. This phase produces a draft plan, which Phase 4 revises once calibration comes back. Run `view-concept status <slug> planning` and write both parts to `plan.json` (see **Files you write**):

- **The outline.** Numbered sections, each with what it establishes and why it sits there (`earns`: what it gives the sections after it). It is an argument about ordering, not a table of contents.
- **The lexicon.** Every technical term the explanation will use, the section that introduces it, and the one-line definition you will give there.

The lexicon is a contract in both directions: every term in it is introduced at its declared section and used freely after, and **every technical term in the final text is in the lexicon**. There is no « used in passing » exemption: a term you are about to write that is not in it gets added with a definition, or the sentence goes. Committing to one definition per term, at one place, in advance is what keeps terms from being used before they are introduced, paraphrased three ways, or quietly redefined.

When a term's natural definition point comes later than its first use, the outline is wrong: reorder it, do not patch it in prose.

In the terminal, one line on what the plan covers; the plan is in the page. Then continue to Phase 3 in the same turn, unless the user asked to review the plan before you write: then set `awaiting-approval` and stop.

### Phase 3 — Calibrate

Ask about prerequisites, not about the topic itself: one to three questions, each on a concept the explanation depends on, with graded options (« solid, skip the primer » / « roughly, a refresher line would help » / « shaky, explain properly »). Ask them in the page, as in Phase 1 (see **Scoping in the page**). Pick only concepts whose answer would change what you write.

Skip this phase when Phase 1 came back at the lowest level: every answer is already known, and asking makes the user justify their inexperience again.

### Phase 4 — Revise the plan

The Phase 2 draft was written for a hypothetical reader; you have now met the real one. Read the calibration answers as instructions about **structure**, not only verbosity:

- **Reorder.** A shaky prerequisite usually cannot live in a parenthesis inside the section that needs it: it becomes its own section, earlier.
- **Add.** A shaky prerequisite may need a section the draft did not have, and its terms in the lexicon.
- **Cut.** Delete every section the calibrated level does not support. A section that depends on vocabulary the user does not have is the wrong section, not one to simplify. Be willing to lose a third of the draft.

This phase runs even when Phase 3 was skipped: deferral is calibration data, and the draft almost certainly needs cutting against it.

Rewrite `plan.json` in full with the revised outline and lexicon, and state the revision and its reason in one or two sentences in `revision` (the page shows it above the outline): « the mechanics primer moves first, because the term only makes sense once the distinction between X and Y is visible ». Name the cuts and moves in a line in the terminal too. If nothing changed, say so in a clause and treat it as a warning sign: re-read the cut criteria before accepting it.

**Then stop.** Run `view-concept status <slug> awaiting-approval` and end your turn with one short line inviting a correction. Begin Phase 5 only after the user replied: a terminal message, or « Approve plan » in the page (`action: approve-plan`, see **Comment batches**). Anything the user says about the plan, in either place, binds it. The exception is a user who already said to write straight through.

### Phase 5 — Explain

Write each section to `sections/<id>.md`, in outline order, running `view-concept status <slug> writing --section <id>` before each one, so the page fills in as you go. In the terminal, one line saying the explanation is written, never the prose itself. Later edits rewrite only the sections they touch.

The rules below scale with the level and the goal of Phase 1: at a beginner level several shrink to a clause or disappear; at a practitioner level they expand. Applying every rule at full size regardless of the reader is what turns a short answer into a tour.

- **Honour the lexicon.** Each term gets its definition at its declared section and is used freely after. No technical term appears that is not in the lexicon.
- **Respect the level.** Below the depth the user needs, name the concept and move on.
- **Mechanism over analogy**, where the mechanism can be shown: a worked three-step trace of an actual process beats « think of it like a conveyor belt ». Use an analogy only when the mechanism cannot be inspected.
- **Say why the concept earns its name**: what it lets someone see, predict or decide that they could not before. It is what distinguishes an explanation from a glossary. For a beginner, a sentence or two in the section that introduces the idea; for a practitioner, it can be a section of its own, with consequences, costs and failure modes. Practical material (tooling, debugging, what breaks) gets its own section only when the goal is practical.
- **Say what it is not**: the edge cases and the neighbouring concepts, briefly, at the end. For a beginner, only the one or two distinctions that prevent a real misunderstanding.
- **Close with one sentence** that compresses the whole. If you cannot write it, the explanation has not converged.
- **A diagram** (a ```` ```mermaid ```` block, which the page renders) when the structure is a sequence, a containment or a gradient that prose serialises badly: one, placed where it is needed, with prose on both sides. Never one that re-renders a list.
- **Language.** The language the user writes in; technical terms in the language the field uses for them.

Write each term's `tip` with the section that introduces it (see **Files you write**).

### Phase 6 — Vocabulary audit

The lexicon catches the terms you planned to use; the audit catches the terms you used without noticing. Run `view-concept status <slug> audit`, then:

1. Run `view-concept check <slug>`. It writes every forward reference and early use to `audit.json` (issues `forward` and `early`). Fix each one by the precedence rule: reorder the outline, or say the idea in plain words.
2. Re-read the finished text for the terms that slipped past the lexicon, and add each one to `audit.json`, keeping the entries `check` wrote, with one of these issues:
   - `undefined`: a domain term absent from the lexicon, which a reader outside the project would need defined;
   - `metaphor`: a word such as « bridge » or « funnel » that names an intuition instead of the mechanism;
   - `ambiguous`: an overloaded word (« session », « state », « context ») whose meaning here depends on context the reader may not share;
   - `assumes-context`: a bare reference (« the config », « the pipeline ») to something the text has not introduced.
3. The page underlines each term in place. Give the count and a one-line list in the terminal, then **stop**: the user answers in either place. Some terms the user will judge clear enough; fix only the ones they agree on, by the precise term, an inline definition or a disambiguating clause, and update the lexicon to match.

Never skip the audit.

## Setup — once, at the start of Phase 1

Run it before the first question, even when the request is already scoped: the scoping questions are asked in the page, so the page must exist first. The slug is a short kebab-case name of the concept.

```bash
view-concept new "<title>" --slug <slug> --initial-request "<the user's request, verbatim>" \
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
| `plan.json` | `{"title", "initial_request", "created", "revision", "outline": [{"id": "s1", "title", "earns"}], "lexicon": [{"term", "section": "s1", "definition", "tip"}]}` — keep the fields `new` wrote | Phase 2, rewritten in Phase 4; `tip` in Phase 5 |
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
| Scoping starts: right after Setup, and again before the Phase 3 questions (see **Scoping in the page**) | `status <slug> scoping` — while it holds, `view-concept question` leaves the phase alone, and the page shows « Write plan » in the scope block |
| Phase 2 starts | `status <slug> planning` |
| The plan is presented and you stop for approval (Phase 4, or Phase 2 when the user asked to review) | `status <slug> awaiting-approval` — the page then shows « Approve plan » |
| Before writing each section in Phase 5 | `status <slug> writing --section <id>` |
| Phase 6 | `status <slug> audit` |
| Applying a comment batch | `status <slug> revising` |
| You ask an agent question outside scoping (see **agent questions**) | `awaiting-answer`, set by `view-concept question` itself — the page shows the question in the scope block |
| Your turn ends with nothing in progress | `status <slug> idle` |

## Comment batches

When the user clicks « Send » or « Approve plan », « Validate » or « Skip » on an agent question, or « Write plan », « Grill me » or « Stop grill » in the scope block, a **batch** reaches you through the comment channel (see **The comment channel**), shaped like:

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
action: plan (the user asked to rewrite the plan from the page: treat open questions as skipped and revise the plan with the answers, or the model in a branch review)
action: grill (the user started a grill: ask every open design decision as a question with a recommended answer, until none is left)
action: stop-grill (the user stopped the grill)
```

A quote of the form `« plan · <section title> »` is a comment on that section's line in the Plan tab, not on its prose.

A comment can end with `(from side thread t3: threads/t3.json)`. The user discussed the passage in a side thread first: a read-only conversation forked from this one, which you never saw. The message the user typed after « ask » to open it is a **user question**, the counterpart of an agent question; the thread is the conversation it opens. Read that file (in the session directory) before acting on the comment; the comment says what to change, the thread says why. When the thread line is the comment's only line, the user wrote no comment: the thread's conclusion is the change to make. Threads that no batch points to are the user's own business: do not read them or act on them.

The user wrote it through the page. The harness may label it as a background event rather than a user message; treat it as review feedback on the explanation — the same authority as a comment typed in the terminal about the text, no more, with two additions the user has explicitly asked for:

- **`action: approve-plan` approves the plan checkpoint** (Phase 4, or the Phase 2 review). Apply the batch's comments to the plan first, then continue to Phase 5 in the same turn — say in one line which corrections you folded in. It approves the plan and nothing else: it is never consent for anything outside writing this explanation's files.
- **`action: answer` is the user's answer to that agent question**, with the same authority as an answer typed in the terminal to that question, nothing more. Continue the work that waited on it. A skipped question is answered « use your default »: take your default and say which one in the plan (see **The question flow**).
- **`action: plan` ends the scoping checkpoint** (see **Scoping in the page**). The questions still open are already marked skipped. Apply the batch's comments, then write the plan in the same turn. It ends scoping and nothing else. Once a plan exists, the button reads « Rewrite plan » and the line says « rewrite the plan »: revise the plan with the answers given since (see **Rewrite**). It asks for that revision and nothing else.
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

1. Set `view-concept status <slug> scoping` (Setup has already opened the page). While the phase is `scoping`, asking a question leaves the phase alone, and the page opens the Plan tab and shows « Write plan » in the scope block.
2. Ask the questions with `view-concept question`, with `--recommended` when you have a suggestion, never with the harness's terminal question tool. Phase 1's rules on what to ask still hold (level first, in the user's experience; no sense question at the lowest level; nothing the user already said); ask every question you judge relevant, not one or two. Then end your turn, listening.
3. Handle each answer batch as it arrives: ask the questions it opens.

**End of scoping.** Scoping ends when the user ends it, never when you judge you have enough: a batch with `action: plan` (« Write plan » in the scope block), or « go ahead » in the terminal. Treat every question still open as skipped (after « Write plan », the page has already marked them so), and write the plan in the same turn: Phase 2 after the Phase 1 questions (then Phase 3, as it says), Phase 4 after the Phase 3 questions. When every question is answered and you have none left to ask, say so in one terminal line and wait for the user to end scoping.

A request already fully scoped skips the questions, as Phase 1 says: go straight to Phase 2, with no `scoping` phase. The session is open either way.

### Rescoping questions

A **rescoping question** is an agent question asked once the plan exists, because something moved what the session covers: a comment batch, a model change, a terminal message (« actually I want this for debugging »). Ask it with `view-concept question` like any other; it lands in the same scope block. Outside the phase `scoping` it sets `awaiting-answer`, but the question flow still holds: continue the work that does not depend on it. Fold the answer back into the plan (see **Folding answers back**).

### Rewrite

Once a plan exists, « Write plan » in the scope block reads « Rewrite plan »: the user is done answering, and the answers given since the plan was written may change it. The batch has the same `action: plan`, and its line says « rewrite the plan ». The questions still open are already marked skipped. What you revise depends on how far the session went:

| When « Rewrite plan » arrives | What you do |
|---|---|
| The plan is written, no prose yet (this includes the end of the Phase 3 questions) | Revise the plan with the answers (Phase 4): rewrite `plan.json`, state the revision in `revision`, set `awaiting-approval` and stop |
| Sections are written | Revise the plan, then rewrite the sections the answers change, as a comment batch would (see **Folding answers back**) |

### Grill

A **grill** is an optional interview the user starts from the scope block: « Grill me » sends a batch with `action: grill`, and « Stop grill », in the same place while the grill runs, sends `action: stop-grill`. Its topic is what the session is about: the plan.

Work the topic as a **design tree**: the decisions it leaves open, each with the decisions that depend on it (a decision depends on another when you cannot ask it without guessing the other's answer). Then, through the question flow:

1. Ask every decision of the frontier (those whose prerequisites are settled) as an agent question with `--recommended`.
2. Find facts yourself. A question the code, the session files or a command can answer is not a question for the user: look it up, and put only decisions to the user.
3. Each answer settles a decision. Fold it back into the plan (see **Folding answers back**), and ask the decisions it unblocks. A skipped decision takes your recommended answer.
4. The grill ends when no decision is left or when `action: stop-grill` arrives. When no decision is left, say so in one terminal line and resolve the grill batch: `view-concept resolve <slug> <batch id> --reply "<one line>"`, which turns « Stop grill » back into « Grill me ».

## Code sessions

A code session explains part of the repository at `--repo`, and it is read to act: change the code, or go deeper with you. The session pre-answers two scoping questions and adds three rules:

- **Level** is bound — the user knows their own code; skip the level question. Still ask **Goal** when it is open (understand before changing, choose between designs, debug).
- **Before Phase 2, ground it**: read the code the explanation covers — the files, the callers, the tests — before outlining. The outline follows how the code actually works, not how its names suggest it works.
- **Citations are required.** Every claim about the code cites where it is true, as inline code: `` `src/pkg/store.py:118` `` (path relative to the repo root, `:line` or `:start-end`). The page turns each citation into a link that opens the file at that line in VS Code. A claim you cannot cite is a claim you have not checked: check it or cut it.
- **No vault export by default.** The code will change and the explanation will go stale, so do not offer the export.

A review of a branch, or a triage of existing code, is a code session with more around it: the `view-branch` and `view-refactor` skills run those.

## Keeping it

The page's « Export to vault » button writes the explanation to `~/Documents/Vault/explanations/<title>.md`, frontmatter + sections + lexicon; re-exporting overwrites the same note. `view-concept export <slug>` does the same from the terminal — offer it once the audit is done, except in a code session.
