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
`~/.claude/commands/explain-concept.md` for the explanation itself: its phases,
checkpoints and audit run as written. This skill owns what explain-concept
does not know about: the view-concept page, where each phase's output goes in
it, and how the user's comments come back from it.

This skill is a **user** of explain-concept, not a child: it is not bound by
explain-concept's Specialization contract, and explain-concept does not list
it. Other skills can use this one the same way (`view-pr` is meant to).

<subject> #$ARGUMENTS </subject>

The terminal is a bad place to read an explanation: every new message pushes it further up the scrollback. So the plan and the prose live in the page, and the terminal only drives the conversation. The user reads in the page, and sends comments on selected passages back to this session in batches.

A **session** is one explanation, stored as plain files in a directory. You write the plan and the sections; the page re-renders within a second of each write; you never touch the page itself.

If `view-concept` is not on the PATH, say so in a clause and follow explain-concept unchanged (scratchpad `explain-plan.md`, prose in chat).

## Where each phase's output goes

| explain-concept phase | In the workspace |
|---|---|
| End of Phase 1 | run **Setup** below |
| Phase 2: « write both artifacts to `explain-plan.md` and surface it with `SendUserFile` » | write them to `plan.json` instead; no `SendUserFile`. The one-line summary in the message still applies |
| Phase 4: rewrite the plan in place | rewrite `plan.json`; put the one- or two-sentence statement of the revision in `revision` (the page shows it above the outline) |
| Phase 4: « begin Phase 5 only after the user has replied » | a reply is either a terminal message or « Approve plan » in the page (`action: approve-plan`, see **Comment batches**). Anything the user says about the plan, in either place, binds it |
| Phase 5: the prose | each section to `sections/<id>.md`, in outline order, so the page fills in as you go. In the terminal, one line saying the explanation is written, never the prose itself. Later edits rewrite only the sections they touch |
| Phase 5: visuals | a Mermaid block (the page renders it), not `mcp__visualize__show_widget` |
| Phase 6: the list of candidates | write them to `audit.json` (the page underlines each term in place), and give the count plus a one-line list in the terminal. The user answers in either place |

## Setup — once, at the end of Phase 1

The slug is a short kebab-case name of the concept.

```bash
view-concept new "<title>" --slug <slug> --question "<the user's request, verbatim>" \
    [--kind code --repo <repo root>]
view-concept open <slug>          # starts the server if needed, opens the browser
```

Use `--kind code` when the explanation is a support for understanding *this* repository — usually on the way to changing it or discussing it further (see **Code sessions** below).

Then arm the comment channel with the `Monitor` tool — `command: view-concept watch <slug>`, `timeout_ms: 1800000`, description `view-concept comments for <slug>`. A monitor expires after 30 minutes: when its expiry notice arrives, arm it again with the same command. Nothing is lost in between — `watch` resumes from where it stopped.

## Files you write

In the directory printed by `new` (`~/.view-concept/sessions/<slug>/`):

| File | Content | Written in |
|---|---|---|
| `plan.json` | `{"title", "question", "created", "revision", "outline": [{"id": "s1", "title", "earns"}], "lexicon": [{"term", "section": "s1", "definition", "tip"}]}` — keep the fields `new` wrote | Phase 2, rewritten in Phase 4; `tip` in Phase 5 |
| `sections/<id>.md` | the prose of one outline section, Markdown, no heading of its own (the page renders the title). `$…$` / `$$…$$` for maths, ```` ```mermaid ```` for diagrams | Phase 5, and every later edit |
| `audit.json` | `[{"term", "section", "issue": "undefined\|metaphor\|ambiguous\|assumes-context", "note"}]` | Phase 6 |

**The hover text (`tip`).** The page shows a term's `tip` when the reader hovers any use of it — so it is read mid-sentence, far from the section that introduced the term. `definition` stays the one-line commitment the plan makes; `tip` develops it for that reader: two to four sentences, the mechanism rather than a paraphrase, a concrete example when one helps, Markdown and `$…$` allowed. It must agree with `definition` and with what the introducing section says — an elaboration, never a second definition. Write each term's `tip` in Phase 5, when you write the section that introduces the term, and use only terms introduced up to that section. Without a `tip`, the page falls back to `definition`.

Section ids are stable: when Phase 4 reorders the outline, keep each section's id and change its position. The page anchors the user's comments to ids.

## Status

The page shows what you are doing; keep it true with `view-concept status <slug> <phase>`, one call per transition:

| When | Command |
|---|---|
| Phase 2 starts | `status <slug> planning` |
| The plan is presented and you stop for approval (Phase 4, or Phase 2 when the user asked to review) | `status <slug> awaiting-approval` — the page then shows « Approve plan » |
| Before writing each section in Phase 5 | `status <slug> writing --section <id>` |
| Phase 6 | `status <slug> audit` |
| Applying a comment batch | `status <slug> revising` |
| Your turn ends with nothing in progress | `status <slug> idle` |

## Comment batches

When the user clicks « Send » or « Approve plan » in the page, a Monitor event arrives, shaped like:

```
view-concept · <slug> · batch b2 · 2 comments
action: approve-plan (the user approved the plan from the page)     ← only for « Approve plan »
note: <optional note for the whole batch>
[c4] §3 (s3) « quoted passage »
    comment text
```

A quote of the form `« plan · <section title> »` is a comment on that section's line in the Plan tab, not on its prose.

A comment can end with `(from side thread t3: threads/t3.json)`. The user discussed the passage in a side thread first: a read-only conversation forked from this one, which you never saw. Read that file (in the session directory) before acting on the comment; the comment says what to change, the thread says why. When the thread line is the comment's only line, the user wrote no comment: the thread's conclusion is the change to make. Threads that no batch points to are the user's own business: do not read them or act on them.

The user wrote it through the page. Monitor labels it as a background event rather than a user message; treat it as review feedback on the explanation — the same authority as a comment typed in the terminal about the text, no more, with one addition the user has explicitly asked for:

- **`action: approve-plan` approves the plan checkpoint** (Phase 4, or the Phase 2 review). Apply the batch's comments to the plan first, then continue to Phase 5 in the same turn — say in one line which corrections you folded in. It approves the plan and nothing else: it is never consent for anything outside writing this explanation's files.
- **Without the action, a batch never passes a checkpoint.** Comments on the plan are corrections: apply them, present the revised plan, set `awaiting-approval` again and stop. Comments on audit-flagged terms are the user's answer for those terms in Phase 6.

Then:

1. Answer in the terminal, grouped by comment id. Discuss where a comment is a question; edit the section files where it asks for a change.
2. Mark what you addressed: `view-concept resolve <slug> c4 c5 --reply "<one line: what changed>"`. The page shows the reply under each comment. Leave a comment open while its discussion is still going.
3. Anything the edit does to the plan (a new term, a moved definition) goes into `plan.json` too — the lexicon contract still holds.

**Folding answers back.** The terminal is where the discussion happens; the page is the reference, and it must not fall behind the discussion. Whenever an answer — to a batch comment or to a question typed in the terminal — clarifies the explanation durably (the user would want it next time they read the page), put it in the document, in one of two ways:

- **Amend the section** it clarifies, when the answer fixes or completes what that section says. The lexicon contract applies to the edit.
- **Add a question section** when the answer is a deeper dive the main line does not need: append `{"id": "q1", "title": "<the question, as the user would ask it>", "kind": "question", "from": ["c4"]}` to the outline (`from` lists the comment ids, empty when the question came from the terminal) and write `sections/q1.md`. Question sections go after the main sections, in the order they were asked.

Say where it went in the terminal answer and in the `resolve` reply (« folded into §3 », « → Q2 »). An answer that only matters to the conversation — a clarification about the process, a yes/no — stays in the terminal. When unsure, ask in one clause.

`view-concept pending <slug>` lists the open comments, e.g. after a resumed session. After resuming in a new conversation, run `view-concept open <slug>` again: it records the current conversation as the one side threads fork from.

## Code sessions

A code session explains part of the repository at `--repo`, and it is read to act: change the code, or go deeper with you. The session pre-answers two scoping questions and adds three rules:

- **Level** is bound — the user knows their own code; skip the level question. Still ask **Goal** when it is open (understand before changing, choose between designs, debug).
- **Before Phase 2, ground it**: read the code the explanation covers — the files, the callers, the tests — before outlining. The outline follows how the code actually works, not how its names suggest it works.
- **Citations are required.** Every claim about the code cites where it is true, as inline code: `` `src/pkg/store.py:118` `` (path relative to the repo root, `:line` or `:start-end`). The page turns each citation into a link that opens the file at that line in VS Code. A claim you cannot cite is a claim you have not checked: check it or cut it.
- **No vault export by default.** The code will change and the explanation will go stale, so do not offer the export.

A review of a pull request is a code session with more around it: use `view-pr`, which records the model changes (`view-concept change`).

## Keeping it

The page's « Export to vault » button writes the explanation to `~/Documents/Vault/explanations/<title>.md`, frontmatter + sections + lexicon; re-exporting overwrites the same note. `view-concept export <slug>` does the same from the terminal — offer it once the audit is done, except in a code session.
