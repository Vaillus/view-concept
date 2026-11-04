# view-concept

The explanation skill: `SKILL.md` is what the coordinator follows, the main session of a skill that only routes each comment batch to a role agent and does none of the work itself, and `roles/` holds the instructions of those role agents, each an agent the coordinator starts for one part of the work, from the session folder.

## Files

```
SKILL.md                  # the coordinator: the session's setup, the choice between questions first and the subject drawn first, which role each event goes to
roles/scoper.md           # the drawing of the subject, its pins and its terms, built with the user before any prose, for an idea that needs morphing first
roles/planner.md          # the outline and the terms of the explanation: from questions on the user's level, or converted from the scoper's drawing, the scoper's terms carried into it
roles/writer.md           # the prose of the explanation, or the report written from the drawing, and the vocabulary audit
roles/planning-rules.md   # the rules for changing the outline and the terms, read by the planner and the writer
```

## Two paths

The coordinator picks one of two paths from the request; you may ask for one, and the coordinator takes it into account but decides:

- the **direct path**, a request for an explanation run through the six phases of `/view-concept`, for a straightforward explanation: the planner asks the Scope questions (your level, the sense of the word, the goal) and the Calibrate questions (on the prerequisite concepts), and stops for « Approve plan », then the writer writes the prose and runs the vocabulary audit, every technical term of the prose checked against the lexicon;
- the **scoping path**, a request for an explanation whose subject is drawn first, for an idea that needs morphing before it can be explained: the scoper draws the subject with you until « End scoping », the button that ends the drawing; the planner then converts the drawing into the outline, gives each entry of the lexicon the scoper wrote its home section (see **The drawing and its pins**), and the writer writes the report from it. No Scope or Calibrate question is asked and no « Approve plan » stop comes: the probes and the prerequisite trees on the drawing do that work.

Nothing records the path as a setting: a session is on the scoping path once its outline holds the **drawing**, a section marked `"part": "scoping"` (`sections/scoping.html`), and the page's scoping tab, the export and the published page read the path from it. A session with a drawing stays on the scoping path.

The scoper, the planner and the writer are role agents, each an agent the coordinator starts for one part of the work, from the session folder; a side thread on an explanation starts from that folder too, never from the conversation the session was started in. The three role files started from `/build-feature`'s, and a rule the two skills share is written in both: a change to one is a change to the other.

## The drawing and its pins

The drawing is the subject drawn step by step with you, before any section of prose is written. The **scoper**, the agent that builds it, redraws it once per comment batch and adds no substantial part by itself: what it finds is offered as a lead beside an **element** (one piece of the drawing, with an id of its own, `e1`, `e2`…, that pins and comments point to), and enters the drawing only once you take it.

Its open points are pins ([`src/view_concept/README.md`](../../src/view_concept/README.md#pins)), of five kinds:

| Kind | Sits on | You settle it by |
|---|---|---|
| **probe** | an element you drew, asking what you actually believe on that point | answering with what you believe, right or wrong |
| **correction** | an element you drew, stating that it is wrong or imprecise, and the fix | accepting the fix or defending your point |
| **tension** | two of your elements that do not sit together, or one that contradicts your goal | saying which side gives way |
| **choice** | the subject, where it has several framings, asking which one the explanation follows | picking the framing |
| **lead** | beside an element, offering something the agent found, with its sources when it looked it up | taking it or leaving it |

You answer a pin by a comment or a side thread on its box; on a correction or a lead, the box's « agree » button drafts the comment « agreed » for you, which accepts the fix or takes the lead ([`src/view_concept/README.md`](../../src/view_concept/README.md#pins)). The scoper closes the pin at its next redraw. It also closes, with no comment of yours, an open pin a decision drawn since makes moot, a **withdrawn pin**, its note « withdrawn: » followed by that decision, or contradicts, a **replaced pin**: the scoper opens a new pin in its new form, with an id of its own, and the old pin's note reads « replaced by <new pin id>: » followed by the decision. The drawing's first line names both. An open correction or tension holds « End scoping » back; a probe, a choice or a lead left open is left out of the report.

A **sent thread** is a side thread whose conclusion you sent to the comment batch with « → batch », with or without a comment of yours, and the scoper reads it whole. What you took in it (an answer, « option 1 », an explicit « agreed ») is drawn, citing the thread, and so is its conclusion when you send it with no text: a thread sent with no text is your agreement. Whatever else the thread agent put forward, a definition, a fact, a framing or a decision, is not drawn: each opens as a lead citing the thread, on the run that reads it.

An element can carry a **prerequisite tree**: the concepts it rests on, drawn above it level by level, each answered yes, quickly or no. Yes opens the concept's text box, a short explanation of it, and grows its own prerequisites above it; quickly opens a one-sentence text box and grows none; no stops the branch. The drawing's script asks for the tree's rows and texts through the **channel**, the path a section's script uses to ask an agent for data, and keeps your answers in the **parameters file**, `params.json`, never in the drawing, so a redraw loses none of them (both in [`src/view_concept/README.md`](../../src/view_concept/README.md#the-channel)). The planner and the writer read that file to give each prerequisite the depth you chose: a full explanation, one sentence, or its name at most.

The scoper also writes the lexicon of `plan.json` from its first drawing on: an entry for each term of the drawing that is not plain language, `{"term", "section": "scoping", "definition"}`, with no `kind` and no `tip`, which the page underlines in the drawing with its definition on hover. You rename a term or change its definition by a comment on it where it is underlined. The **scoping lexicon** is the lexicon's entries while their **home section**, the section that introduces the term, is the scoping section. « End scoping » changes only that: the planner sets each entry's home section to the section of the report that introduces its term, and keeps its term and its definition. A return to scoping keeps the home sections a conversion set, unless the next conversion removes an entry's section from the outline, which gives the entry the section that now introduces its term; a term the redraw adds enters with `"section": "scoping"` until the next « End scoping ». The precedence check (`view-concept check`), which flags a term used in a section placed before its home section, skips the drawing, which uses every term of the report before that term's home section.

After « End scoping », the session goes back to scoping two ways: the planner or the writer, finding an element wrong or two at odds, opens a correction or a tension with `view-concept pin`, which sets the phase back to `scoping`; or you comment on the drawing or on a pin's box, which goes to the scoper. You then end scoping again, and the writer rewrites only the sections the change touches. A comment on a section of the report goes to the writer.

## The report

The **report** is the explanation a session ends with, exported as an Obsidian note or published as a web page. On the scoping path its reader never saw the drawing and has the same priors as the person who drew it, so the writer states everything the drawing settled, in full, without saying who settled it: « Never tell back », the rule that the prose never explains back what you told the agent, holds on the direct path only. What a lead you took added is cited with its sources.

The report retranscribes the drawing as a sequence of sections in reading order, and no section carries a prerequisite tree. The export and the published page leave the drawing out (`Session.in_report` in `src/view_concept/store.py`).
